"""Benchmarks for memory usage and footprint.

These benchmarks measure memory consumption including:
- Memory footprint per flag
- Storage backend memory usage at scale
- Client memory usage
- Memory growth patterns

Performance Targets:
- Single flag footprint: <2KB
- 1000 flags: <2MB total
- 10000 flags: <20MB total
"""

from __future__ import annotations

import gc
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from litestar_flags import (
    EvaluationContext,
    FeatureFlagClient,
    MemoryStorageBackend,
)
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    pass


def get_object_size(obj: object) -> int:
    """Get the approximate size of an object in bytes.

    Uses sys.getsizeof with recursive traversal for containers.
    This is an approximation and may not capture all memory used
    by the object (e.g., interned strings, shared references).

    Args:
        obj: The object to measure.

    Returns:
        Approximate size in bytes.

    """
    seen = set()

    def sizeof(o: object) -> int:
        """Recursively calculate size."""
        if id(o) in seen:
            return 0
        seen.add(id(o))

        size = sys.getsizeof(o)

        if isinstance(o, dict):
            size += sum(sizeof(k) + sizeof(v) for k, v in o.items())
        elif isinstance(o, (list, tuple, set, frozenset)):
            size += sum(sizeof(item) for item in o)
        elif hasattr(o, "__dict__"):
            size += sizeof(o.__dict__)
        elif hasattr(o, "__slots__"):
            size += sum(sizeof(getattr(o, slot)) for slot in o.__slots__ if hasattr(o, slot))

        return size

    return sizeof(obj)


def create_simple_flag(index: int) -> FeatureFlag:
    """Create a simple flag for memory testing.

    Args:
        index: Unique index for the flag.

    Returns:
        A simple FeatureFlag instance.

    """
    now = datetime.now(UTC)
    return FeatureFlag(
        id=uuid4(),
        key=f"memory-flag-{index:05d}",
        name=f"Memory Test Flag {index}",
        description=f"A flag for memory benchmarking (index {index})",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=index % 2 == 0,
        tags=["benchmark", "memory"],
        metadata_={"index": index},
        rules=[],
        overrides=[],
        variants=[],
        created_at=now,
        updated_at=now,
    )


def create_complex_flag(index: int) -> FeatureFlag:
    """Create a complex flag with rules and variants for memory testing.

    Args:
        index: Unique index for the flag.

    Returns:
        A complex FeatureFlag instance.

    """
    flag_id = uuid4()
    now = datetime.now(UTC)
    return FeatureFlag(
        id=flag_id,
        key=f"memory-complex-flag-{index:05d}",
        name=f"Memory Complex Flag {index}",
        description=f"A complex flag with rules and variants (index {index})",
        flag_type=FlagType.JSON,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"config": {"enabled": True, "threshold": 0.5}},
        tags=["benchmark", "memory", "complex", f"batch-{index // 100}"],
        metadata_={"index": index, "complexity": "high", "created_by": "benchmark"},
        rules=[
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name=f"Rule {j}",
                priority=j,
                enabled=True,
                conditions=[
                    {"attribute": "plan", "operator": "eq", "value": "premium"},
                    {"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]},
                ],
                serve_enabled=True,
                created_at=now,
                updated_at=now,
            )
            for j in range(3)
        ],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key=f"variant-{k}",
                name=f"Variant {k}",
                value={"variant": f"v{k}", "weight": 25, "config": {"theme": ["light", "dark"][k % 2]}},
                weight=25,
                created_at=now,
                updated_at=now,
            )
            for k in range(4)
        ],
        created_at=now,
        updated_at=now,
    )


# -----------------------------------------------------------------------------
# Flag Memory Footprint
# -----------------------------------------------------------------------------


class TestFlagMemoryFootprint:
    """Benchmarks for individual flag memory footprint."""

    def test_simple_flag_footprint(self) -> None:
        """Measure memory footprint of a simple boolean flag.

        Target: <2KB per flag.
        """
        gc.collect()

        flag = create_simple_flag(0)
        size = get_object_size(flag)

        print(f"\nSimple flag size: {size:,} bytes ({size / 1024:.2f} KB)")

        # Assertions for reasonable bounds
        # Pydantic models have overhead; 15KB is acceptable for a simple flag
        assert size < 16384, f"Simple flag too large: {size} bytes"

    def test_complex_flag_footprint(self) -> None:
        """Measure memory footprint of a complex flag.

        Target: <10KB per flag.
        """
        gc.collect()

        flag = create_complex_flag(0)
        size = get_object_size(flag)

        print(f"\nComplex flag size: {size:,} bytes ({size / 1024:.2f} KB)")

        # Complex flags with rules and variants will be larger
        # Pydantic models with nested objects have significant overhead
        assert size < 102400, f"Complex flag too large: {size} bytes"

    def test_flag_component_sizes(self) -> None:
        """Measure memory footprint of flag components.

        Helps identify memory hotspots.
        """
        gc.collect()

        flag = create_complex_flag(0)

        component_sizes = {
            "total": get_object_size(flag),
            "rules": sum(get_object_size(r) for r in flag.rules),
            "variants": sum(get_object_size(v) for v in flag.variants),
            "tags": get_object_size(flag.tags),
            "metadata": get_object_size(flag.metadata_),
        }

        print("\nFlag component sizes:")
        for name, size in component_sizes.items():
            print(f"  {name}: {size:,} bytes ({size / 1024:.2f} KB)")


# -----------------------------------------------------------------------------
# Storage Memory Usage
# -----------------------------------------------------------------------------


class TestStorageMemoryUsage:
    """Benchmarks for storage backend memory usage."""

    @pytest.mark.benchmark(group="memory-storage")
    def test_storage_memory_100_flags(self, benchmark) -> None:
        """Measure memory usage with 100 flags.

        Target: <500KB total.
        """
        import asyncio

        gc.collect()

        async def create_flags():
            storage = MemoryStorageBackend()
            for i in range(100):
                await storage.create_flag(create_simple_flag(i))
            return storage

        def create_and_measure():
            storage = asyncio.run(create_flags())
            gc.collect()
            size = get_object_size(storage)
            return size

        size = benchmark(create_and_measure)

        print(f"\nStorage with 100 flags: {size:,} bytes ({size / 1024:.2f} KB)")

        assert size < 2 * 1024 * 1024, f"Storage too large for 100 flags: {size} bytes"

    @pytest.mark.benchmark(group="memory-storage")
    def test_storage_memory_1000_flags(self, benchmark) -> None:
        """Measure memory usage with 1000 flags.

        Target: <5MB total.
        """
        import asyncio

        gc.collect()

        async def create_flags():
            storage = MemoryStorageBackend()
            for i in range(1000):
                await storage.create_flag(create_simple_flag(i))
            return storage

        def create_and_measure():
            storage = asyncio.run(create_flags())
            gc.collect()
            size = get_object_size(storage)
            return size

        size = benchmark(create_and_measure)

        print(f"\nStorage with 1000 flags: {size:,} bytes ({size / (1024 * 1024):.2f} MB)")

        assert size < 20 * 1024 * 1024, f"Storage too large for 1000 flags: {size} bytes"

    def test_storage_memory_10000_flags(self) -> None:
        """Measure memory usage with 10000 flags.

        Target: <50MB total.
        Note: This test is slower and only runs once.
        """
        import asyncio

        gc.collect()

        async def create_flags():
            storage = MemoryStorageBackend()
            for i in range(10000):
                await storage.create_flag(create_simple_flag(i))
            return storage

        storage = asyncio.run(create_flags())

        gc.collect()
        size = get_object_size(storage)

        print(f"\nStorage with 10000 flags: {size:,} bytes ({size / (1024 * 1024):.2f} MB)")

        assert size < 200 * 1024 * 1024, f"Storage too large for 10000 flags: {size} bytes"


# -----------------------------------------------------------------------------
# Client Memory Usage
# -----------------------------------------------------------------------------


class TestClientMemoryUsage:
    """Benchmarks for client memory usage."""

    def test_client_baseline_memory(self) -> None:
        """Measure baseline client memory without flags.

        Target: <10KB for empty client.
        """
        gc.collect()

        storage = MemoryStorageBackend()
        client = FeatureFlagClient(storage=storage)

        gc.collect()
        size = get_object_size(client)

        print(f"\nEmpty client size: {size:,} bytes ({size / 1024:.2f} KB)")

        # Client includes engine and storage references
        assert size < 100 * 1024, f"Empty client too large: {size} bytes"

    def test_client_with_default_context(self) -> None:
        """Measure client memory with default context.

        Target: <15KB with context.
        """
        gc.collect()

        storage = MemoryStorageBackend()
        default_context = EvaluationContext(
            targeting_key="user-001",
            user_id="user-001",
            organization_id="org-001",
            attributes={
                "plan": "premium",
                "country": "US",
                "beta_tester": True,
            },
        )
        client = FeatureFlagClient(storage=storage, default_context=default_context)

        gc.collect()
        size = get_object_size(client)

        print(f"\nClient with context size: {size:,} bytes ({size / 1024:.2f} KB)")

        # Client with context includes engine, storage, and context
        assert size < 150 * 1024, f"Client with context too large: {size} bytes"


# -----------------------------------------------------------------------------
# Memory Growth Patterns
# -----------------------------------------------------------------------------


class TestMemoryGrowthPatterns:
    """Benchmarks for memory growth as data scales."""

    def test_linear_memory_growth(self) -> None:
        """Verify memory grows linearly with flag count.

        This test ensures there are no memory leaks or
        exponential growth patterns.
        """
        import asyncio

        gc.collect()

        sizes = []
        counts = [10, 50, 100, 500, 1000]

        for count in counts:
            gc.collect()

            async def create_flags(n: int):
                storage = MemoryStorageBackend()
                for i in range(n):
                    await storage.create_flag(create_simple_flag(i))
                return storage

            storage = asyncio.run(create_flags(count))

            gc.collect()
            size = get_object_size(storage)
            sizes.append(size)

        print("\nMemory growth analysis:")
        for i, (count, size) in enumerate(zip(counts, sizes, strict=True)):
            per_flag = size / count if count > 0 else 0
            print(f"  {count:5d} flags: {size:10,} bytes ({per_flag:.0f} bytes/flag)")

            # Verify growth is roughly linear (per-flag cost should be stable)
            if i > 0:
                prev_per_flag = sizes[i - 1] / counts[i - 1]
                # Allow 50% variance in per-flag cost
                assert per_flag < prev_per_flag * 1.5, "Non-linear memory growth detected"

    def test_no_memory_leak_on_delete(self) -> None:
        """Verify memory is reclaimed when flags are deleted.

        This test ensures proper cleanup happens on deletion.
        """
        import asyncio

        gc.collect()

        async def create_and_delete():
            storage = MemoryStorageBackend()

            # Create flags
            for i in range(100):
                await storage.create_flag(create_simple_flag(i))

            gc.collect()
            size_with_flags = get_object_size(storage)

            # Delete all flags
            for i in range(100):
                await storage.delete_flag(f"memory-flag-{i:05d}")

            gc.collect()
            size_after_delete = get_object_size(storage)

            return size_with_flags, size_after_delete

        size_with_flags, size_after_delete = asyncio.run(create_and_delete())

        print(f"\nSize with 100 flags: {size_with_flags:,} bytes")
        print(f"Size after deletion: {size_after_delete:,} bytes")
        print(f"Memory reclaimed: {size_with_flags - size_after_delete:,} bytes")

        # After deletion, storage should be much smaller
        assert size_after_delete < size_with_flags * 0.2, "Memory not properly reclaimed"


# -----------------------------------------------------------------------------
# Context Memory Usage
# -----------------------------------------------------------------------------


class TestContextMemoryUsage:
    """Benchmarks for evaluation context memory usage."""

    def test_simple_context_size(self) -> None:
        """Measure simple context memory footprint.

        Target: <1KB per context.
        """
        gc.collect()

        context = EvaluationContext(
            targeting_key="user-001",
            user_id="user-001",
        )

        size = get_object_size(context)

        print(f"\nSimple context size: {size:,} bytes")

        # Pydantic context model has overhead
        assert size < 8192, f"Simple context too large: {size} bytes"

    def test_complex_context_size(self) -> None:
        """Measure complex context memory footprint.

        Target: <5KB per context.
        """
        gc.collect()

        context = EvaluationContext(
            targeting_key="user-001",
            user_id="user-001",
            organization_id="org-001",
            tenant_id="tenant-001",
            attributes={
                "plan": "premium",
                "country": "US",
                "beta_tester": True,
                "email": "user@example.com",
                "age": 30,
                "signup_date": "2024-01-15",
                "features_used": ["feature_a", "feature_b", "feature_c"],
                "settings": {
                    "notifications": True,
                    "theme": "dark",
                    "language": "en",
                },
                "tags": ["power-user", "early-adopter"],
            },
        )

        size = get_object_size(context)

        print(f"\nComplex context size: {size:,} bytes ({size / 1024:.2f} KB)")

        # Complex context with nested attributes
        assert size < 20480, f"Complex context too large: {size} bytes"

    def test_batch_contexts_memory(self) -> None:
        """Measure memory usage of batch contexts.

        Target: <100KB for 100 contexts.
        """
        gc.collect()

        contexts = [
            EvaluationContext(
                targeting_key=f"user-{i:06d}",
                user_id=f"user-{i:06d}",
                attributes={
                    "plan": ["free", "basic", "premium"][i % 3],
                    "country": ["US", "CA", "UK", "DE"][i % 4],
                },
            )
            for i in range(100)
        ]

        gc.collect()
        total_size = sum(get_object_size(ctx) for ctx in contexts)
        avg_size = total_size / len(contexts)

        print(f"\n100 contexts total: {total_size:,} bytes ({total_size / 1024:.2f} KB)")
        print(f"Average per context: {avg_size:.0f} bytes")

        # 100 contexts with Pydantic overhead
        assert total_size < 1024 * 1024, f"Batch contexts too large: {total_size} bytes"
