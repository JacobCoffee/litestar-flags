"""Benchmark fixtures for litestar-flags performance testing.

This module provides fixtures for benchmarking flag evaluation,
storage operations, and memory usage at various scales.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from litestar_flags import (
    EvaluationContext,
    FeatureFlagClient,
    MemoryStorageBackend,
)
from litestar_flags.engine import EvaluationEngine
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.variant import FlagVariant
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    pass


# -----------------------------------------------------------------------------
# Storage Backend Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def storage() -> MemoryStorageBackend:
    """Create a memory storage backend for benchmarking."""
    return MemoryStorageBackend()


@pytest.fixture
def engine() -> EvaluationEngine:
    """Create an evaluation engine for benchmarking."""
    return EvaluationEngine()


@pytest.fixture
async def client(storage: MemoryStorageBackend) -> FeatureFlagClient:
    """Create a feature flag client for benchmarking."""
    return FeatureFlagClient(storage=storage)


# -----------------------------------------------------------------------------
# Flag Complexity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def simple_boolean_flag() -> FeatureFlag:
    """Create a simple boolean flag with no rules.

    This represents the minimum complexity flag for baseline benchmarks.
    Target: <1ms evaluation time.
    """
    return FeatureFlag(
        id=uuid4(),
        key="simple-flag",
        name="Simple Boolean Flag",
        description="A simple feature flag with no rules",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        tags=["benchmark"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_single_rule() -> FeatureFlag:
    """Create a flag with a single targeting rule.

    Tests evaluation performance with basic rule matching.
    """
    flag_id = uuid4()
    return FeatureFlag(
        id=flag_id,
        key="single-rule-flag",
        name="Single Rule Flag",
        description="Flag with one targeting rule",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["benchmark"],
        metadata_={},
        rules=[
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Premium Users",
                priority=0,
                enabled=True,
                conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
                serve_enabled=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def flag_with_multiple_rules() -> FeatureFlag:
    """Create a flag with multiple targeting rules.

    Tests evaluation performance with complex rule matching.
    Contains 5 rules with various operators and conditions.
    """
    flag_id = uuid4()
    now = datetime.now(UTC)
    return FeatureFlag(
        id=flag_id,
        key="multi-rule-flag",
        name="Multi Rule Flag",
        description="Flag with multiple targeting rules",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["benchmark", "complex"],
        metadata_={},
        rules=[
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Enterprise Users",
                priority=0,
                enabled=True,
                conditions=[{"attribute": "plan", "operator": "eq", "value": "enterprise"}],
                serve_enabled=True,
                created_at=now,
                updated_at=now,
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Premium US Users",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "plan", "operator": "eq", "value": "premium"},
                    {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
                ],
                serve_enabled=True,
                created_at=now,
                updated_at=now,
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Beta Testers",
                priority=2,
                enabled=True,
                conditions=[{"attribute": "beta_tester", "operator": "eq", "value": True}],
                serve_enabled=True,
                created_at=now,
                updated_at=now,
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Internal Users",
                priority=3,
                enabled=True,
                conditions=[{"attribute": "email", "operator": "ends_with", "value": "@company.com"}],
                serve_enabled=True,
                created_at=now,
                updated_at=now,
            ),
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="50% Rollout",
                priority=4,
                enabled=True,
                conditions=[],
                serve_enabled=True,
                rollout_percentage=50,
                created_at=now,
                updated_at=now,
            ),
        ],
        overrides=[],
        variants=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def flag_with_variants() -> FeatureFlag:
    """Create an A/B test flag with variants.

    Tests evaluation performance with variant selection.
    Contains control and treatment variants with 50/50 split.
    """
    flag_id = uuid4()
    now = datetime.now(UTC)
    return FeatureFlag(
        id=flag_id,
        key="ab-test-flag",
        name="A/B Test Flag",
        description="Flag with A/B test variants",
        flag_type=FlagType.STRING,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"variant": "control"},
        tags=["benchmark", "experiment"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="control",
                name="Control",
                value={"variant": "control", "button_color": "blue"},
                weight=50,
                created_at=now,
                updated_at=now,
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="treatment",
                name="Treatment",
                value={"variant": "treatment", "button_color": "green"},
                weight=50,
                created_at=now,
                updated_at=now,
            ),
        ],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def flag_with_multi_variants() -> FeatureFlag:
    """Create a multivariate flag with 4 variants.

    Tests evaluation performance with multiple variant selections.
    Contains 4 variants with 25% weight each.
    """
    flag_id = uuid4()
    now = datetime.now(UTC)
    return FeatureFlag(
        id=flag_id,
        key="multi-variant-flag",
        name="Multi Variant Flag",
        description="Flag with 4 variants",
        flag_type=FlagType.JSON,
        status=FlagStatus.ACTIVE,
        default_enabled=True,
        default_value={"variant": "control"},
        tags=["benchmark", "experiment"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="control",
                name="Control",
                value={"variant": "control", "config": {"theme": "default"}},
                weight=25,
                created_at=now,
                updated_at=now,
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="variant-a",
                name="Variant A",
                value={"variant": "a", "config": {"theme": "dark"}},
                weight=25,
                created_at=now,
                updated_at=now,
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="variant-b",
                name="Variant B",
                value={"variant": "b", "config": {"theme": "light"}},
                weight=25,
                created_at=now,
                updated_at=now,
            ),
            FlagVariant(
                id=uuid4(),
                flag_id=flag_id,
                key="variant-c",
                name="Variant C",
                value={"variant": "c", "config": {"theme": "compact"}},
                weight=25,
                created_at=now,
                updated_at=now,
            ),
        ],
        created_at=now,
        updated_at=now,
    )


# -----------------------------------------------------------------------------
# Context Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def simple_context() -> EvaluationContext:
    """Create a simple evaluation context."""
    return EvaluationContext(
        targeting_key="user-benchmark-001",
        user_id="user-benchmark-001",
    )


@pytest.fixture
def complex_context() -> EvaluationContext:
    """Create a complex evaluation context with many attributes."""
    return EvaluationContext(
        targeting_key="user-benchmark-002",
        user_id="user-benchmark-002",
        organization_id="org-001",
        tenant_id="tenant-001",
        attributes={
            "plan": "premium",
            "country": "US",
            "beta_tester": True,
            "email": "user@company.com",
            "age": 30,
            "signup_date": "2024-01-15",
            "features_used": ["feature_a", "feature_b"],
            "settings": {"notifications": True, "theme": "dark"},
        },
    )


# -----------------------------------------------------------------------------
# Scale Fixtures
# -----------------------------------------------------------------------------


def create_flag(index: int) -> FeatureFlag:
    """Create a flag with the given index.

    Args:
        index: Unique index for the flag.

    Returns:
        A FeatureFlag instance.

    """
    flag_id = uuid4()
    now = datetime.now(UTC)
    return FeatureFlag(
        id=flag_id,
        key=f"flag-{index:05d}",
        name=f"Flag {index}",
        description=f"Benchmark flag number {index}",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=index % 2 == 0,
        tags=["benchmark", f"batch-{index // 100}"],
        metadata_={"index": index},
        rules=[],
        overrides=[],
        variants=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def flags_100() -> list[FeatureFlag]:
    """Create 100 flags for batch benchmarks."""
    return [create_flag(i) for i in range(100)]


@pytest.fixture
def flags_1000() -> list[FeatureFlag]:
    """Create 1000 flags for batch benchmarks."""
    return [create_flag(i) for i in range(1000)]


@pytest.fixture
def flags_10000() -> list[FeatureFlag]:
    """Create 10000 flags for large scale benchmarks."""
    return [create_flag(i) for i in range(10000)]


@pytest.fixture
async def storage_100(storage: MemoryStorageBackend, flags_100: list[FeatureFlag]) -> MemoryStorageBackend:
    """Create storage with 100 flags pre-loaded."""
    for flag in flags_100:
        await storage.create_flag(flag)
    return storage


@pytest.fixture
async def storage_1000(storage: MemoryStorageBackend, flags_1000: list[FeatureFlag]) -> MemoryStorageBackend:
    """Create storage with 1000 flags pre-loaded."""
    for flag in flags_1000:
        await storage.create_flag(flag)
    return storage


@pytest.fixture
async def storage_10000(storage: MemoryStorageBackend, flags_10000: list[FeatureFlag]) -> MemoryStorageBackend:
    """Create storage with 10000 flags pre-loaded."""
    for flag in flags_10000:
        await storage.create_flag(flag)
    return storage


# -----------------------------------------------------------------------------
# Context Generation
# -----------------------------------------------------------------------------


def create_context(index: int) -> EvaluationContext:
    """Create a unique evaluation context for the given index.

    Args:
        index: Unique index for the context.

    Returns:
        An EvaluationContext instance.

    """
    return EvaluationContext(
        targeting_key=f"user-{index:06d}",
        user_id=f"user-{index:06d}",
        attributes={
            "plan": ["free", "basic", "premium", "enterprise"][index % 4],
            "country": ["US", "CA", "UK", "DE", "FR"][index % 5],
        },
    )


@pytest.fixture
def contexts_100() -> list[EvaluationContext]:
    """Create 100 unique contexts for batch evaluation."""
    return [create_context(i) for i in range(100)]


@pytest.fixture
def contexts_1000() -> list[EvaluationContext]:
    """Create 1000 unique contexts for batch evaluation."""
    return [create_context(i) for i in range(1000)]
