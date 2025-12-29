"""Benchmarks for storage backend performance.

These benchmarks measure storage backend operations including:
- Single flag retrieval (get_flag)
- Batch flag retrieval (get_flags, get_all_active_flags)
- Flag creation and updates
- Override operations

Performance Targets:
- get_flag: <0.5ms for memory backend
- get_all_active_flags with 100 flags: <5ms
- get_all_active_flags with 1000 flags: <50ms
- get_all_active_flags with 10000 flags: <500ms
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.override import FlagOverride
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from litestar_flags import MemoryStorageBackend


# -----------------------------------------------------------------------------
# Single Flag Operations
# -----------------------------------------------------------------------------


class TestGetFlag:
    """Benchmarks for single flag retrieval."""

    @pytest.mark.benchmark(group="storage-get")
    def test_get_flag_exists(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving an existing flag by key.

        Target: <0.5ms per operation.
        """

        async def get_flag():
            return await storage_100.get_flag("flag-00050")

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flag()))

        assert result is not None
        assert result.key == "flag-00050"

    @pytest.mark.benchmark(group="storage-get")
    def test_get_flag_not_exists(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving a non-existent flag.

        Target: <0.5ms per operation.
        """

        async def get_flag():
            return await storage_100.get_flag("non-existent-flag")

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flag()))

        assert result is None

    @pytest.mark.benchmark(group="storage-get")
    def test_get_flag_from_10000(
        self,
        benchmark,
        storage_10000: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving a flag from large storage (10000 flags).

        Tests dict lookup performance at scale.
        Target: <0.5ms per operation (dict lookup is O(1)).
        """

        async def get_flag():
            return await storage_10000.get_flag("flag-05000")

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flag()))

        assert result is not None
        assert result.key == "flag-05000"


# -----------------------------------------------------------------------------
# Batch Flag Operations
# -----------------------------------------------------------------------------


class TestGetFlags:
    """Benchmarks for batch flag retrieval."""

    @pytest.mark.benchmark(group="storage-batch")
    def test_get_flags_10(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving 10 flags by keys.

        Target: <1ms total.
        """
        keys = [f"flag-{i:05d}" for i in range(0, 100, 10)]

        async def get_flags():
            return await storage_100.get_flags(keys)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flags()))

        assert len(result) == 10

    @pytest.mark.benchmark(group="storage-batch")
    def test_get_flags_50(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving 50 flags by keys.

        Target: <5ms total.
        """
        keys = [f"flag-{i:05d}" for i in range(0, 1000, 20)]

        async def get_flags():
            return await storage_1000.get_flags(keys)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flags()))

        assert len(result) == 50

    @pytest.mark.benchmark(group="storage-batch")
    def test_get_flags_100(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving 100 flags by keys.

        Target: <10ms total.
        """
        keys = [f"flag-{i:05d}" for i in range(0, 1000, 10)]

        async def get_flags():
            return await storage_1000.get_flags(keys)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flags()))

        assert len(result) == 100


# -----------------------------------------------------------------------------
# Get All Active Flags
# -----------------------------------------------------------------------------


class TestGetAllActiveFlags:
    """Benchmarks for retrieving all active flags."""

    @pytest.mark.benchmark(group="storage-all")
    def test_get_all_active_100(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving all 100 active flags.

        Target: <5ms total.
        """

        async def get_all():
            return await storage_100.get_all_active_flags()

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_all()))

        assert len(result) == 100

    @pytest.mark.benchmark(group="storage-all")
    def test_get_all_active_1000(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving all 1000 active flags.

        Target: <50ms total.
        """

        async def get_all():
            return await storage_1000.get_all_active_flags()

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_all()))

        assert len(result) == 1000

    @pytest.mark.benchmark(group="storage-all")
    def test_get_all_active_10000(
        self,
        benchmark,
        storage_10000: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving all 10000 active flags.

        Target: <500ms total.
        """

        async def get_all():
            return await storage_10000.get_all_active_flags()

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_all()))

        assert len(result) == 10000


# -----------------------------------------------------------------------------
# Write Operations
# -----------------------------------------------------------------------------


class TestWriteOperations:
    """Benchmarks for flag write operations."""

    @pytest.mark.benchmark(group="storage-write")
    def test_create_flag(
        self,
        benchmark,
        storage: MemoryStorageBackend,
    ) -> None:
        """Benchmark creating a single flag.

        Target: <1ms per operation.
        """
        counter = [0]

        def create_flag():
            counter[0] += 1
            now = datetime.now(UTC)
            return FeatureFlag(
                id=uuid4(),
                key=f"benchmark-flag-{counter[0]}",
                name=f"Benchmark Flag {counter[0]}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=True,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=now,
                updated_at=now,
            )

        async def create():
            flag = create_flag()
            return await storage.create_flag(flag)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(create()))

        assert result is not None

    @pytest.mark.benchmark(group="storage-write")
    def test_update_flag(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark updating an existing flag.

        Target: <1ms per operation.
        """

        async def get_and_update():
            flag = await storage_100.get_flag("flag-00050")
            assert flag is not None
            flag.name = f"Updated Flag {datetime.now(UTC)}"
            return await storage_100.update_flag(flag)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_and_update()))

        assert result is not None

    @pytest.mark.benchmark(group="storage-write")
    def test_delete_flag(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        flags_100: list[FeatureFlag],
    ) -> None:
        """Benchmark deleting a flag.

        Target: <1ms per operation.
        """
        counter = [0]

        async def setup():
            for flag in flags_100:
                await storage.create_flag(flag)

        asyncio.get_event_loop().run_until_complete(setup())

        async def delete():
            key = f"flag-{counter[0]:05d}"
            counter[0] += 1
            if counter[0] >= 100:
                counter[0] = 0
            return await storage.delete_flag(key)

        # First pass deletes, subsequent might return False
        benchmark(lambda: asyncio.get_event_loop().run_until_complete(delete()))


# -----------------------------------------------------------------------------
# Override Operations
# -----------------------------------------------------------------------------


class TestOverrideOperations:
    """Benchmarks for flag override operations."""

    @pytest.mark.benchmark(group="storage-override")
    def test_create_override(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark creating an override.

        Target: <1ms per operation.
        """
        counter = [0]

        async def get_flag_and_create_override():
            flag = await storage_100.get_flag("flag-00050")
            assert flag is not None
            counter[0] += 1
            now = datetime.now(UTC)
            override = FlagOverride(
                id=uuid4(),
                flag_id=flag.id,
                entity_type="user",
                entity_id=f"user-{counter[0]}",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            return await storage_100.create_override(override)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_flag_and_create_override()))

        assert result is not None

    @pytest.mark.benchmark(group="storage-override")
    def test_get_override_exists(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving an existing override.

        Target: <0.5ms per operation.
        """

        async def setup():
            flag = await storage_100.get_flag("flag-00050")
            assert flag is not None
            now = datetime.now(UTC)
            override = FlagOverride(
                id=uuid4(),
                flag_id=flag.id,
                entity_type="user",
                entity_id="benchmark-user",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            await storage_100.create_override(override)
            return flag.id

        flag_id = asyncio.get_event_loop().run_until_complete(setup())

        async def get_override():
            return await storage_100.get_override(flag_id, "user", "benchmark-user")

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_override()))

        assert result is not None
        assert result.enabled is True

    @pytest.mark.benchmark(group="storage-override")
    def test_get_override_not_exists(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
    ) -> None:
        """Benchmark retrieving a non-existent override.

        Target: <0.5ms per operation.
        """

        async def get_flag_id():
            flag = await storage_100.get_flag("flag-00050")
            assert flag is not None
            return flag.id

        flag_id = asyncio.get_event_loop().run_until_complete(get_flag_id())

        async def get_override():
            return await storage_100.get_override(flag_id, "user", "non-existent-user")

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(get_override()))

        assert result is None


# -----------------------------------------------------------------------------
# Throughput Tests
# -----------------------------------------------------------------------------


class TestStorageThroughput:
    """Benchmarks for storage throughput."""

    @pytest.mark.benchmark(group="storage-throughput")
    def test_mixed_read_operations(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
    ) -> None:
        """Benchmark mixed read operations (simulating real workload).

        Performs a mix of get_flag, get_flags, and get_all_active_flags.
        Target: <100ms for 100 mixed operations.
        """

        async def mixed_operations():
            results = []
            for i in range(100):
                if i % 10 == 0:
                    # Every 10th: get all active
                    result = await storage_1000.get_all_active_flags()
                    results.append(len(result))
                elif i % 3 == 0:
                    # Every 3rd: batch get
                    keys = [f"flag-{j:05d}" for j in range(i, min(i + 10, 1000))]
                    result = await storage_1000.get_flags(keys)
                    results.append(len(result))
                else:
                    # Otherwise: single get
                    result = await storage_1000.get_flag(f"flag-{i:05d}")
                    results.append(result is not None)
            return results

        results = benchmark(lambda: asyncio.get_event_loop().run_until_complete(mixed_operations()))

        assert len(results) == 100

    @pytest.mark.benchmark(group="storage-throughput")
    def test_sequential_creates(
        self,
        benchmark,
        storage: MemoryStorageBackend,
    ) -> None:
        """Benchmark sequential flag creation throughput.

        Target: <1ms per create on average.
        """
        batch_num = [0]

        async def create_batch():
            batch_num[0] += 1
            flags_created = []
            now = datetime.now(UTC)
            for i in range(100):
                flag = FeatureFlag(
                    id=uuid4(),
                    key=f"throughput-flag-{batch_num[0]}-{i}",
                    name=f"Throughput Flag {batch_num[0]}-{i}",
                    flag_type=FlagType.BOOLEAN,
                    status=FlagStatus.ACTIVE,
                    default_enabled=True,
                    tags=[],
                    metadata_={},
                    rules=[],
                    overrides=[],
                    variants=[],
                    created_at=now,
                    updated_at=now,
                )
                result = await storage.create_flag(flag)
                flags_created.append(result)
            return flags_created

        results = benchmark(lambda: asyncio.get_event_loop().run_until_complete(create_batch()))

        assert len(results) == 100


# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------


class TestHealthCheck:
    """Benchmarks for health check operation."""

    @pytest.mark.benchmark(group="storage-health")
    def test_health_check(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
    ) -> None:
        """Benchmark health check operation.

        Target: <0.1ms per operation.
        """

        async def health_check():
            return await storage_1000.health_check()

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(health_check()))

        assert result is True
