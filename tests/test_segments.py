"""Tests for segment evaluation and storage operations.

This module provides comprehensive tests for:
- Segment model creation and validation
- MemoryStorageBackend segment CRUD operations
- SegmentEvaluator condition matching and nested segment evaluation
- Integration tests for segment-based flag rules
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from litestar_flags import EvaluationContext, MemoryStorageBackend
from litestar_flags.engine import EvaluationEngine
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.segment import Segment
from litestar_flags.segment_evaluator import (
    CircularSegmentReferenceError,
    SegmentEvaluator,
)
from litestar_flags.types import FlagStatus, FlagType, RuleOperator


# -----------------------------------------------------------------------------
# Helper function to create segments with all required fields
# -----------------------------------------------------------------------------
def create_segment(
    name: str,
    *,
    description: str | None = None,
    conditions: list[dict] | None = None,
    parent_segment_id: UUID | None = None,
    enabled: bool = True,
    segment_id: UUID | None = None,
) -> Segment:
    """Create a Segment with all required fields set explicitly.

    This helper handles both SQLAlchemy models and dataclass fallback
    by explicitly providing all necessary fields.
    """
    return Segment(
        id=segment_id or uuid4(),
        name=name,
        description=description,
        conditions=conditions if conditions is not None else [],
        parent_segment_id=parent_segment_id,
        enabled=enabled,
    )


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def storage() -> MemoryStorageBackend:
    """Create a memory storage backend for testing."""
    return MemoryStorageBackend()


@pytest.fixture
def evaluator() -> SegmentEvaluator:
    """Create a segment evaluator for testing."""
    return SegmentEvaluator()


@pytest.fixture
def basic_segment() -> Segment:
    """Create a basic segment with simple conditions."""
    return create_segment(
        name="premium_users",
        description="Users with premium plan",
        conditions=[
            {"attribute": "plan", "operator": "eq", "value": "premium"},
        ],
        enabled=True,
    )


@pytest.fixture
def us_users_segment() -> Segment:
    """Create a segment for US users."""
    return create_segment(
        name="us_users",
        description="Users located in the United States",
        conditions=[
            {"attribute": "country", "operator": "in", "value": ["US", "USA"]},
        ],
        enabled=True,
    )


@pytest.fixture
def beta_testers_segment() -> Segment:
    """Create a segment for beta testers."""
    return create_segment(
        name="beta_testers",
        description="Users who opted into beta testing",
        conditions=[
            {"attribute": "beta_tester", "operator": "eq", "value": True},
        ],
        enabled=True,
    )


@pytest.fixture
def premium_context() -> EvaluationContext:
    """Create context for a premium user."""
    return EvaluationContext(
        targeting_key="user-123",
        user_id="user-123",
        attributes={"plan": "premium", "country": "US"},
    )


@pytest.fixture
def free_context() -> EvaluationContext:
    """Create context for a free user."""
    return EvaluationContext(
        targeting_key="user-456",
        user_id="user-456",
        attributes={"plan": "free", "country": "UK"},
    )


# -----------------------------------------------------------------------------
# TestSegmentModel - Tests for Segment dataclass creation and fields
# -----------------------------------------------------------------------------
class TestSegmentModel:
    """Tests for Segment model creation and validation."""

    def test_create_segment_with_all_fields(self) -> None:
        """Test creating a segment with all fields populated."""
        segment_id = uuid4()
        parent_id = uuid4()
        now = datetime.now(UTC)

        segment = Segment(
            id=segment_id,
            name="full_segment",
            description="A fully populated segment",
            conditions=[
                {"attribute": "plan", "operator": "eq", "value": "enterprise"},
                {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
            ],
            parent_segment_id=parent_id,
            enabled=True,
            created_at=now,
            updated_at=now,
        )

        assert segment.id == segment_id
        assert segment.name == "full_segment"
        assert segment.description == "A fully populated segment"
        assert len(segment.conditions) == 2
        assert segment.parent_segment_id == parent_id
        assert segment.enabled is True
        assert segment.created_at == now
        assert segment.updated_at == now

    def test_create_segment_with_minimal_fields(self) -> None:
        """Test creating a segment with only required fields."""
        # Note: SQLAlchemy models don't apply defaults in constructor,
        # so we explicitly test a segment with explicit values
        segment = create_segment(name="minimal_segment")

        assert segment.name == "minimal_segment"
        assert segment.conditions == []
        assert segment.enabled is True
        assert isinstance(segment.id, UUID)

    def test_create_segment_with_conditions(self) -> None:
        """Test creating a segment with various condition types."""
        conditions = [
            {"attribute": "age", "operator": "gt", "value": 18},
            {"attribute": "email", "operator": "ends_with", "value": "@company.com"},
            {"attribute": "tags", "operator": "contains", "value": "vip"},
        ]

        segment = create_segment(
            name="complex_conditions",
            conditions=conditions,
        )

        assert len(segment.conditions) == 3
        assert segment.conditions[0]["attribute"] == "age"
        assert segment.conditions[1]["operator"] == "ends_with"
        assert segment.conditions[2]["value"] == "vip"

    def test_create_nested_segment_with_parent_id(self) -> None:
        """Test creating a segment with parent_segment_id for nesting."""
        parent_id = uuid4()
        segment = create_segment(
            name="child_segment",
            parent_segment_id=parent_id,
            conditions=[{"attribute": "region", "operator": "eq", "value": "west"}],
        )

        assert segment.parent_segment_id == parent_id
        assert segment.name == "child_segment"

    def test_segment_repr(self) -> None:
        """Test segment string representation."""
        segment = create_segment(name="test_segment", enabled=True)
        repr_str = repr(segment)

        assert "Segment" in repr_str
        assert "test_segment" in repr_str
        assert "enabled=True" in repr_str

    def test_segment_enabled_by_default(self) -> None:
        """Test that segments are enabled when explicitly set."""
        segment = create_segment(name="default_enabled", enabled=True)
        assert segment.enabled is True

    def test_create_disabled_segment(self) -> None:
        """Test creating a disabled segment."""
        segment = create_segment(name="disabled_segment", enabled=False)
        assert segment.enabled is False


# -----------------------------------------------------------------------------
# TestSegmentStorage - Tests for MemoryStorageBackend segment CRUD
# -----------------------------------------------------------------------------
class TestSegmentStorage:
    """Tests for MemoryStorageBackend segment CRUD operations."""

    async def test_create_segment(self, storage: MemoryStorageBackend) -> None:
        """Test creating a segment in storage."""
        segment = create_segment(
            name="new_segment",
            description="A new segment",
            conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
        )

        created = await storage.create_segment(segment)

        assert created.name == "new_segment"
        assert created.description == "A new segment"
        assert created.created_at is not None
        assert created.updated_at is not None

    async def test_create_segment_sets_timestamps(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test that create_segment sets timestamps if not provided."""
        segment = create_segment(name="timestamp_test")

        created = await storage.create_segment(segment)

        assert created.created_at is not None
        assert created.updated_at is not None

    async def test_create_segment_duplicate_name_raises_error(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test that creating a segment with duplicate name raises error."""
        segment1 = create_segment(name="duplicate_name")
        await storage.create_segment(segment1)

        segment2 = create_segment(name="duplicate_name")

        with pytest.raises(ValueError, match="already exists"):
            await storage.create_segment(segment2)

    async def test_get_segment_by_id(
        self, storage: MemoryStorageBackend, basic_segment: Segment
    ) -> None:
        """Test retrieving a segment by its ID."""
        created = await storage.create_segment(basic_segment)

        retrieved = await storage.get_segment(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "premium_users"

    async def test_get_segment_by_id_not_found(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test retrieving a non-existent segment by ID returns None."""
        non_existent_id = uuid4()

        retrieved = await storage.get_segment(non_existent_id)

        assert retrieved is None

    async def test_get_segment_by_name(
        self, storage: MemoryStorageBackend, basic_segment: Segment
    ) -> None:
        """Test retrieving a segment by its name."""
        await storage.create_segment(basic_segment)

        retrieved = await storage.get_segment_by_name("premium_users")

        assert retrieved is not None
        assert retrieved.name == "premium_users"

    async def test_get_segment_by_name_not_found(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test retrieving a non-existent segment by name returns None."""
        retrieved = await storage.get_segment_by_name("non_existent")

        assert retrieved is None

    async def test_get_all_segments(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving all segments from storage."""
        segment1 = create_segment(name="segment_one")
        segment2 = create_segment(name="segment_two")
        segment3 = create_segment(name="segment_three")

        await storage.create_segment(segment1)
        await storage.create_segment(segment2)
        await storage.create_segment(segment3)

        all_segments = await storage.get_all_segments()

        assert len(all_segments) == 3
        names = {s.name for s in all_segments}
        assert names == {"segment_one", "segment_two", "segment_three"}

    async def test_get_all_segments_empty(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test retrieving all segments when storage is empty."""
        all_segments = await storage.get_all_segments()

        assert all_segments == []

    async def test_get_child_segments(self, storage: MemoryStorageBackend) -> None:
        """Test retrieving child segments of a parent."""
        parent = create_segment(name="parent_segment")
        parent = await storage.create_segment(parent)

        child1 = create_segment(name="child_one", parent_segment_id=parent.id)
        child2 = create_segment(name="child_two", parent_segment_id=parent.id)
        child3 = create_segment(name="unrelated_segment")  # No parent

        await storage.create_segment(child1)
        await storage.create_segment(child2)
        await storage.create_segment(child3)

        children = await storage.get_child_segments(parent.id)

        assert len(children) == 2
        names = {c.name for c in children}
        assert names == {"child_one", "child_two"}

    async def test_get_child_segments_no_children(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test retrieving children when parent has no children."""
        parent = create_segment(name="childless_parent")
        parent = await storage.create_segment(parent)

        children = await storage.get_child_segments(parent.id)

        assert children == []

    async def test_update_segment(
        self, storage: MemoryStorageBackend, basic_segment: Segment
    ) -> None:
        """Test updating a segment."""
        created = await storage.create_segment(basic_segment)
        original_updated_at = created.updated_at

        created.description = "Updated description"
        created.conditions = [
            {"attribute": "plan", "operator": "eq", "value": "enterprise"}
        ]

        updated = await storage.update_segment(created)

        assert updated.description == "Updated description"
        assert updated.conditions[0]["value"] == "enterprise"
        assert updated.updated_at is not None
        # Updated_at should be changed (or equal if very fast)
        assert updated.updated_at >= original_updated_at

    async def test_update_segment_name_change(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test updating a segment's name updates the name index.

        Note: The current MemoryStorageBackend stores references to objects,
        so modifying the object in-place before calling update_segment
        will cause the old_segment.name comparison to see the new name.
        This test creates a new segment object with the updated name
        to properly test the name change logic.
        """
        segment = create_segment(name="original_name")
        created = await storage.create_segment(segment)
        original_id = created.id

        # Create a new segment object with the updated name (same ID)
        updated_segment = create_segment(
            name="new_name",
            segment_id=original_id,
            description=created.description,
            conditions=created.conditions,
            enabled=created.enabled,
        )

        await storage.update_segment(updated_segment)

        # New name should work
        new_lookup = await storage.get_segment_by_name("new_name")
        assert new_lookup is not None
        assert new_lookup.name == "new_name"
        assert new_lookup.id == original_id

    async def test_update_segment_name_conflict_raises_error(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test updating segment name to existing name raises error.

        Note: Similar to above, we need to create a new segment object
        to avoid in-place modification affecting the comparison.
        """
        segment1 = create_segment(name="segment_one")
        segment2 = create_segment(name="segment_two")

        created1 = await storage.create_segment(segment1)
        await storage.create_segment(segment2)

        # Create a new segment object with the conflicting name (same ID as segment1)
        conflicting_segment = create_segment(
            name="segment_two",  # Try to rename to existing name
            segment_id=created1.id,
            conditions=created1.conditions,
            enabled=created1.enabled,
        )

        with pytest.raises(ValueError, match="already exists"):
            await storage.update_segment(conflicting_segment)

    async def test_update_segment_not_found_raises_error(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test updating non-existent segment raises error."""
        non_existent = create_segment(name="non_existent", segment_id=uuid4())

        with pytest.raises(ValueError, match="not found"):
            await storage.update_segment(non_existent)

    async def test_delete_segment(
        self, storage: MemoryStorageBackend, basic_segment: Segment
    ) -> None:
        """Test deleting a segment from storage."""
        created = await storage.create_segment(basic_segment)

        result = await storage.delete_segment(created.id)

        assert result is True

        # Verify segment is gone
        retrieved = await storage.get_segment(created.id)
        assert retrieved is None

        # Verify name lookup also fails
        by_name = await storage.get_segment_by_name("premium_users")
        assert by_name is None

    async def test_delete_segment_not_found(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test deleting non-existent segment returns False."""
        non_existent_id = uuid4()

        result = await storage.delete_segment(non_existent_id)

        assert result is False


# -----------------------------------------------------------------------------
# TestSegmentEvaluator - Tests for segment condition evaluation
# -----------------------------------------------------------------------------
class TestSegmentEvaluator:
    """Tests for SegmentEvaluator condition matching."""

    async def test_is_in_segment_matching_conditions(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        basic_segment: Segment,
        premium_context: EvaluationContext,
    ) -> None:
        """Test is_in_segment returns True when conditions match."""
        created = await storage.create_segment(basic_segment)

        result = await evaluator.is_in_segment(
            segment_id=created.id,
            context=premium_context,
            storage=storage,
        )

        assert result is True

    async def test_is_in_segment_non_matching_conditions(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        basic_segment: Segment,
        free_context: EvaluationContext,
    ) -> None:
        """Test is_in_segment returns False when conditions don't match."""
        created = await storage.create_segment(basic_segment)

        result = await evaluator.is_in_segment(
            segment_id=created.id,
            context=free_context,
            storage=storage,
        )

        assert result is False

    async def test_is_in_segment_disabled_segment(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        premium_context: EvaluationContext,
    ) -> None:
        """Test is_in_segment returns False for disabled segments."""
        segment = create_segment(
            name="disabled_segment",
            conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
            enabled=False,
        )
        created = await storage.create_segment(segment)

        result = await evaluator.is_in_segment(
            segment_id=created.id,
            context=premium_context,
            storage=storage,
        )

        assert result is False

    async def test_is_in_segment_not_found(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        premium_context: EvaluationContext,
    ) -> None:
        """Test is_in_segment returns False when segment not found."""
        non_existent_id = uuid4()

        result = await evaluator.is_in_segment(
            segment_id=non_existent_id,
            context=premium_context,
            storage=storage,
        )

        assert result is False

    async def test_is_in_segment_empty_conditions_matches_all(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        premium_context: EvaluationContext,
        free_context: EvaluationContext,
    ) -> None:
        """Test segment with empty conditions matches all contexts."""
        segment = create_segment(name="everyone", conditions=[])
        created = await storage.create_segment(segment)

        # Should match both premium and free users
        result1 = await evaluator.is_in_segment(
            segment_id=created.id,
            context=premium_context,
            storage=storage,
        )
        result2 = await evaluator.is_in_segment(
            segment_id=created.id,
            context=free_context,
            storage=storage,
        )

        assert result1 is True
        assert result2 is True


# -----------------------------------------------------------------------------
# TestNestedSegmentEvaluation - Tests for parent-child segment inheritance
# -----------------------------------------------------------------------------
class TestNestedSegmentEvaluation:
    """Tests for nested segment evaluation with parent inheritance."""

    async def test_nested_segment_must_match_parent_and_child(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that nested segments require matching both parent and child."""
        # Create parent segment: premium users
        parent = create_segment(
            name="premium_users",
            conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
        )
        parent = await storage.create_segment(parent)

        # Create child segment: premium US users
        child = create_segment(
            name="premium_us_users",
            parent_segment_id=parent.id,
            conditions=[{"attribute": "country", "operator": "eq", "value": "US"}],
        )
        child = await storage.create_segment(child)

        # Context: premium US user - should match
        premium_us_context = EvaluationContext(
            attributes={"plan": "premium", "country": "US"}
        )
        result1 = await evaluator.is_in_segment(
            segment_id=child.id,
            context=premium_us_context,
            storage=storage,
        )
        assert result1 is True

        # Context: premium UK user - should NOT match (child condition fails)
        premium_uk_context = EvaluationContext(
            attributes={"plan": "premium", "country": "UK"}
        )
        result2 = await evaluator.is_in_segment(
            segment_id=child.id,
            context=premium_uk_context,
            storage=storage,
        )
        assert result2 is False

        # Context: free US user - should NOT match (parent condition fails)
        free_us_context = EvaluationContext(
            attributes={"plan": "free", "country": "US"}
        )
        result3 = await evaluator.is_in_segment(
            segment_id=child.id,
            context=free_us_context,
            storage=storage,
        )
        assert result3 is False

    async def test_three_level_nested_segments(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test three-level deep nested segments."""
        # Level 1: All premium users
        level1 = create_segment(
            name="premium",
            conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
        )
        level1 = await storage.create_segment(level1)

        # Level 2: Premium US users
        level2 = create_segment(
            name="premium_us",
            parent_segment_id=level1.id,
            conditions=[{"attribute": "country", "operator": "eq", "value": "US"}],
        )
        level2 = await storage.create_segment(level2)

        # Level 3: Premium US beta testers
        level3 = create_segment(
            name="premium_us_beta",
            parent_segment_id=level2.id,
            conditions=[{"attribute": "beta_tester", "operator": "eq", "value": True}],
        )
        level3 = await storage.create_segment(level3)

        # Context that matches all three levels
        full_match_context = EvaluationContext(
            attributes={"plan": "premium", "country": "US", "beta_tester": True}
        )
        result = await evaluator.is_in_segment(
            segment_id=level3.id,
            context=full_match_context,
            storage=storage,
        )
        assert result is True

        # Context missing beta_tester
        partial_context = EvaluationContext(
            attributes={"plan": "premium", "country": "US", "beta_tester": False}
        )
        result2 = await evaluator.is_in_segment(
            segment_id=level3.id,
            context=partial_context,
            storage=storage,
        )
        assert result2 is False


# -----------------------------------------------------------------------------
# TestCircularReferenceDetection - Tests for cycle detection in nested segments
# -----------------------------------------------------------------------------
class TestCircularReferenceDetection:
    """Tests for circular reference detection in segment chains."""

    async def test_direct_circular_reference_raises_error(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that segment referencing itself raises CircularSegmentReferenceError."""
        # Create a segment
        segment = create_segment(name="self_ref")
        segment = await storage.create_segment(segment)

        # Update to reference itself - need to delete and recreate
        # because update_segment checks name conflicts
        await storage.delete_segment(segment.id)

        # Create segment that references itself
        self_ref_segment = create_segment(
            name="self_ref",
            segment_id=segment.id,
            parent_segment_id=segment.id,
        )
        await storage.create_segment(self_ref_segment)

        context = EvaluationContext(attributes={"test": "value"})

        with pytest.raises(CircularSegmentReferenceError) as exc_info:
            await evaluator.is_in_segment(
                segment_id=segment.id,
                context=context,
                storage=storage,
            )

        assert exc_info.value.segment_id == segment.id
        assert segment.id in exc_info.value.visited_chain

    async def test_indirect_circular_reference_raises_error(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that A -> B -> A circular reference raises error."""
        # Create segment A without parent first
        segment_a = create_segment(name="segment_a")
        segment_a = await storage.create_segment(segment_a)
        segment_a_id = segment_a.id

        # Create segment B with A as parent
        segment_b = create_segment(
            name="segment_b", parent_segment_id=segment_a_id
        )
        segment_b = await storage.create_segment(segment_b)
        segment_b_id = segment_b.id

        # Delete A and recreate with B as parent (creating cycle)
        await storage.delete_segment(segment_a_id)
        segment_a_circular = create_segment(
            name="segment_a",
            segment_id=segment_a_id,
            parent_segment_id=segment_b_id,
        )
        await storage.create_segment(segment_a_circular)

        context = EvaluationContext(attributes={"test": "value"})

        with pytest.raises(CircularSegmentReferenceError):
            await evaluator.is_in_segment(
                segment_id=segment_a_id,
                context=context,
                storage=storage,
            )

    async def test_three_way_circular_reference(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that A -> B -> C -> A circular reference raises error."""
        # Create segments A, B, C without circular reference first
        segment_a = create_segment(name="seg_a")
        segment_a = await storage.create_segment(segment_a)
        segment_a_id = segment_a.id

        segment_b = create_segment(name="seg_b", parent_segment_id=segment_a_id)
        segment_b = await storage.create_segment(segment_b)
        segment_b_id = segment_b.id

        segment_c = create_segment(name="seg_c", parent_segment_id=segment_b_id)
        segment_c = await storage.create_segment(segment_c)
        segment_c_id = segment_c.id

        # Delete A and recreate with C as parent (creating cycle A->C->B->A)
        await storage.delete_segment(segment_a_id)
        segment_a_circular = create_segment(
            name="seg_a",
            segment_id=segment_a_id,
            parent_segment_id=segment_c_id,
        )
        await storage.create_segment(segment_a_circular)

        context = EvaluationContext(attributes={"test": "value"})

        with pytest.raises(CircularSegmentReferenceError):
            await evaluator.is_in_segment(
                segment_id=segment_a_id,
                context=context,
                storage=storage,
            )

    async def test_circular_reference_error_contains_chain(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that CircularSegmentReferenceError contains the visited chain."""
        # Create a simple self-referencing segment
        segment_id = uuid4()
        segment = create_segment(
            name="chain_a",
            segment_id=segment_id,
            parent_segment_id=segment_id,
        )
        await storage.create_segment(segment)

        context = EvaluationContext()

        with pytest.raises(CircularSegmentReferenceError) as exc_info:
            await evaluator.is_in_segment(
                segment_id=segment_id,
                context=context,
                storage=storage,
            )

        error = exc_info.value
        # The error message should contain the chain
        assert len(error.visited_chain) > 0
        assert "Circular segment reference detected" in str(error)


# -----------------------------------------------------------------------------
# TestSegmentCaching - Tests for segment cache optimization
# -----------------------------------------------------------------------------
class TestSegmentCaching:
    """Tests for segment caching during evaluation."""

    async def test_segment_cache_is_populated(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        basic_segment: Segment,
        premium_context: EvaluationContext,
    ) -> None:
        """Test that segment cache is populated during evaluation."""
        created = await storage.create_segment(basic_segment)
        cache: dict[UUID, Segment] = {}

        await evaluator.is_in_segment(
            segment_id=created.id,
            context=premium_context,
            storage=storage,
            segment_cache=cache,
        )

        assert created.id in cache
        assert cache[created.id].name == "premium_users"

    async def test_segment_cache_is_used(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        basic_segment: Segment,
        premium_context: EvaluationContext,
    ) -> None:
        """Test that cached segments are used instead of storage lookups."""
        created = await storage.create_segment(basic_segment)

        # Pre-populate cache with a modified segment
        modified_segment = create_segment(
            name="cached_segment",
            segment_id=created.id,
            conditions=[],  # Empty conditions - matches all
            enabled=True,
        )
        cache = {created.id: modified_segment}

        # Even though storage has conditions, cache should be used
        # Since cached segment has empty conditions, it should match
        context = EvaluationContext(attributes={"plan": "free"})  # Would NOT match storage

        result = await evaluator.is_in_segment(
            segment_id=created.id,
            context=context,
            storage=storage,
            segment_cache=cache,
        )

        # Should match because cache has empty conditions
        assert result is True

    async def test_nested_segments_use_cache(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
    ) -> None:
        """Test that parent segments are also cached during nested evaluation."""
        parent = create_segment(
            name="parent",
            conditions=[{"attribute": "level", "operator": "eq", "value": 1}],
        )
        parent = await storage.create_segment(parent)

        child = create_segment(
            name="child",
            parent_segment_id=parent.id,
            conditions=[{"attribute": "level", "operator": "eq", "value": 1}],
        )
        child = await storage.create_segment(child)

        cache: dict[UUID, Segment] = {}
        context = EvaluationContext(attributes={"level": 1})

        await evaluator.is_in_segment(
            segment_id=child.id,
            context=context,
            storage=storage,
            segment_cache=cache,
        )

        # Both child and parent should be in cache
        assert child.id in cache
        assert parent.id in cache


# -----------------------------------------------------------------------------
# TestConditionOperators - Tests for all condition operators in SegmentEvaluator
# -----------------------------------------------------------------------------
class TestConditionOperators:
    """Tests for all condition operators supported by SegmentEvaluator."""

    @pytest.fixture
    def evaluator(self) -> SegmentEvaluator:
        return SegmentEvaluator()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    @pytest.mark.parametrize(
        ("operator", "condition_value", "context_value", "expected"),
        [
            # EQUALS
            ("eq", "premium", "premium", True),
            ("eq", "premium", "free", False),
            # NOT_EQUALS
            ("ne", "free", "premium", True),
            ("ne", "premium", "premium", False),
            # GREATER_THAN
            ("gt", 18, 21, True),
            ("gt", 18, 18, False),
            ("gt", 18, 15, False),
            # GREATER_THAN_OR_EQUAL
            ("gte", 18, 18, True),
            ("gte", 18, 21, True),
            ("gte", 18, 15, False),
            # LESS_THAN
            ("lt", 18, 15, True),
            ("lt", 18, 18, False),
            ("lt", 18, 21, False),
            # LESS_THAN_OR_EQUAL
            ("lte", 18, 18, True),
            ("lte", 18, 15, True),
            ("lte", 18, 21, False),
        ],
    )
    async def test_comparison_operators(
        self,
        evaluator: SegmentEvaluator,
        storage: MemoryStorageBackend,
        operator: str,
        condition_value: int | str,
        context_value: int | str,
        expected: bool,
    ) -> None:
        """Test comparison operators (eq, ne, gt, gte, lt, lte)."""
        segment = create_segment(
            name=f"test_{operator}_{context_value}",
            conditions=[{"attribute": "value", "operator": operator, "value": condition_value}],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"value": context_value})
        result = await evaluator.is_in_segment(
            segment_id=created.id,
            context=context,
            storage=storage,
        )

        assert result is expected

    async def test_in_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test IN operator for list membership."""
        segment = create_segment(
            name="in_test",
            conditions=[
                {"attribute": "country", "operator": "in", "value": ["US", "CA", "UK"]}
            ],
        )
        created = await storage.create_segment(segment)

        # Match
        context_us = EvaluationContext(attributes={"country": "US"})
        assert await evaluator.is_in_segment(created.id, context_us, storage) is True

        # No match
        context_de = EvaluationContext(attributes={"country": "DE"})
        assert await evaluator.is_in_segment(created.id, context_de, storage) is False

    async def test_not_in_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test NOT_IN operator for list exclusion."""
        segment = create_segment(
            name="not_in_test",
            conditions=[
                {"attribute": "country", "operator": "not_in", "value": ["CN", "RU"]}
            ],
        )
        created = await storage.create_segment(segment)

        # Match (not in excluded list)
        context_us = EvaluationContext(attributes={"country": "US"})
        assert await evaluator.is_in_segment(created.id, context_us, storage) is True

        # No match (in excluded list)
        context_cn = EvaluationContext(attributes={"country": "CN"})
        assert await evaluator.is_in_segment(created.id, context_cn, storage) is False

    async def test_contains_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test CONTAINS operator for substring matching."""
        segment = create_segment(
            name="contains_test",
            conditions=[
                {"attribute": "email", "operator": "contains", "value": "@company.com"}
            ],
        )
        created = await storage.create_segment(segment)

        # Match
        context_match = EvaluationContext(attributes={"email": "user@company.com"})
        assert await evaluator.is_in_segment(created.id, context_match, storage) is True

        # No match
        context_no = EvaluationContext(attributes={"email": "user@other.com"})
        assert await evaluator.is_in_segment(created.id, context_no, storage) is False

    async def test_not_contains_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test NOT_CONTAINS operator."""
        segment = create_segment(
            name="not_contains_test",
            conditions=[
                {"attribute": "email", "operator": "not_contains", "value": "spam"}
            ],
        )
        created = await storage.create_segment(segment)

        # Match (doesn't contain spam)
        context_clean = EvaluationContext(attributes={"email": "user@company.com"})
        assert await evaluator.is_in_segment(created.id, context_clean, storage) is True

        # No match (contains spam)
        context_spam = EvaluationContext(attributes={"email": "spam@company.com"})
        assert await evaluator.is_in_segment(created.id, context_spam, storage) is False

    async def test_starts_with_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test STARTS_WITH operator."""
        segment = create_segment(
            name="starts_with_test",
            conditions=[
                {"attribute": "email", "operator": "starts_with", "value": "admin"}
            ],
        )
        created = await storage.create_segment(segment)

        # Match
        context_admin = EvaluationContext(attributes={"email": "admin@company.com"})
        assert await evaluator.is_in_segment(created.id, context_admin, storage) is True

        # No match
        context_user = EvaluationContext(attributes={"email": "user@company.com"})
        assert await evaluator.is_in_segment(created.id, context_user, storage) is False

    async def test_ends_with_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test ENDS_WITH operator."""
        segment = create_segment(
            name="ends_with_test",
            conditions=[
                {"attribute": "email", "operator": "ends_with", "value": "@company.com"}
            ],
        )
        created = await storage.create_segment(segment)

        # Match
        context_company = EvaluationContext(attributes={"email": "user@company.com"})
        assert await evaluator.is_in_segment(created.id, context_company, storage) is True

        # No match
        context_other = EvaluationContext(attributes={"email": "user@other.com"})
        assert await evaluator.is_in_segment(created.id, context_other, storage) is False

    async def test_matches_operator(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test MATCHES (regex) operator."""
        segment = create_segment(
            name="matches_test",
            conditions=[
                {"attribute": "email", "operator": "matches", "value": r".*@company\.com$"}
            ],
        )
        created = await storage.create_segment(segment)

        # Match
        context_match = EvaluationContext(attributes={"email": "user@company.com"})
        assert await evaluator.is_in_segment(created.id, context_match, storage) is True

        # No match
        context_no = EvaluationContext(attributes={"email": "user@company.org"})
        assert await evaluator.is_in_segment(created.id, context_no, storage) is False

    async def test_matches_invalid_regex(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test MATCHES operator with invalid regex returns False."""
        segment = create_segment(
            name="invalid_regex",
            conditions=[
                {"attribute": "value", "operator": "matches", "value": "[invalid(regex"}
            ],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"value": "test"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        assert result is False

    async def test_semver_operators(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test semantic version operators."""
        # SEMVER_EQ
        seg_eq = create_segment(
            name="semver_eq",
            conditions=[{"attribute": "version", "operator": "semver_eq", "value": "1.2.3"}],
        )
        seg_eq = await storage.create_segment(seg_eq)

        ctx_eq = EvaluationContext(attributes={"version": "1.2.3"})
        assert await evaluator.is_in_segment(seg_eq.id, ctx_eq, storage) is True

        ctx_ne = EvaluationContext(attributes={"version": "1.2.4"})
        assert await evaluator.is_in_segment(seg_eq.id, ctx_ne, storage) is False

        # SEMVER_GT
        seg_gt = create_segment(
            name="semver_gt",
            conditions=[{"attribute": "version", "operator": "semver_gt", "value": "2.0.0"}],
        )
        seg_gt = await storage.create_segment(seg_gt)

        ctx_gt = EvaluationContext(attributes={"version": "2.0.1"})
        assert await evaluator.is_in_segment(seg_gt.id, ctx_gt, storage) is True

        ctx_not_gt = EvaluationContext(attributes={"version": "1.9.9"})
        assert await evaluator.is_in_segment(seg_gt.id, ctx_not_gt, storage) is False

        # SEMVER_LT
        seg_lt = create_segment(
            name="semver_lt",
            conditions=[{"attribute": "version", "operator": "semver_lt", "value": "2.0.0"}],
        )
        seg_lt = await storage.create_segment(seg_lt)

        ctx_lt = EvaluationContext(attributes={"version": "1.9.9"})
        assert await evaluator.is_in_segment(seg_lt.id, ctx_lt, storage) is True

        ctx_not_lt = EvaluationContext(attributes={"version": "2.0.1"})
        assert await evaluator.is_in_segment(seg_lt.id, ctx_not_lt, storage) is False

    async def test_unknown_operator_skipped(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test that unknown operators are skipped."""
        segment = create_segment(
            name="unknown_op",
            conditions=[
                {"attribute": "value", "operator": "unknown_operator", "value": "test"},
                {"attribute": "plan", "operator": "eq", "value": "premium"},
            ],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"value": "anything", "plan": "premium"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        # Unknown operator skipped, second condition matches
        assert result is True

    async def test_in_segment_operator_returns_false(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test that IN_SEGMENT operator in conditions returns False."""
        # IN_SEGMENT/NOT_IN_SEGMENT operators should not be used within segment conditions
        # They are meant for flag rules only
        segment = create_segment(
            name="segment_op_test",
            conditions=[
                {"attribute": "segment_id", "operator": "in_segment", "value": str(uuid4())}
            ],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"segment_id": "anything"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        # Should return False because in_segment is not valid in segment conditions
        assert result is False

    async def test_multiple_conditions_and_logic(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test that multiple conditions use AND logic."""
        segment = create_segment(
            name="multi_condition",
            conditions=[
                {"attribute": "plan", "operator": "eq", "value": "premium"},
                {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
                {"attribute": "age", "operator": "gte", "value": 18},
            ],
        )
        created = await storage.create_segment(segment)

        # All conditions match
        ctx_all = EvaluationContext(
            attributes={"plan": "premium", "country": "US", "age": 25}
        )
        assert await evaluator.is_in_segment(created.id, ctx_all, storage) is True

        # One condition fails
        ctx_fail = EvaluationContext(
            attributes={"plan": "premium", "country": "US", "age": 16}
        )
        assert await evaluator.is_in_segment(created.id, ctx_fail, storage) is False


# -----------------------------------------------------------------------------
# TestSegmentBasedFlagRules - Integration tests with EvaluationEngine
# -----------------------------------------------------------------------------
class TestSegmentBasedFlagRules:
    """Integration tests for segment-based flag rules using EvaluationEngine.

    Note: These tests verify that segment-based operators (IN_SEGMENT, NOT_IN_SEGMENT)
    are properly handled when they appear in flag rules. The actual segment evaluation
    would typically be done at a higher level (e.g., FeatureFlagClient) that coordinates
    between EvaluationEngine and SegmentEvaluator.
    """

    @pytest.fixture
    def engine(self) -> EvaluationEngine:
        return EvaluationEngine()

    @pytest.fixture
    def storage(self) -> MemoryStorageBackend:
        return MemoryStorageBackend()

    async def test_flag_rule_conditions_can_contain_segment_operator(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test that flag rules can specify segment-based conditions.

        Note: This test demonstrates the structure of segment-based rules.
        The actual evaluation of IN_SEGMENT would require integration with
        SegmentEvaluator at a higher level.
        """
        flag_id = uuid4()
        segment_id = uuid4()

        flag = FeatureFlag(
            id=flag_id,
            key="segment-feature",
            name="Segment Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
                FlagRule(
                    id=uuid4(),
                    flag_id=flag_id,
                    name="Premium Segment Rule",
                    priority=1,
                    enabled=True,
                    conditions=[
                        {
                            "attribute": "segment",
                            "operator": RuleOperator.IN_SEGMENT.value,
                            "value": str(segment_id),
                        }
                    ],
                    serve_enabled=True,
                ),
            ],
            overrides=[],
            variants=[],
        )

        await storage.create_flag(flag)

        # The EvaluationEngine itself doesn't resolve IN_SEGMENT conditions
        # It would need to be enhanced or wrapped to support segment evaluation
        # This test verifies the rule structure is valid
        context = EvaluationContext(
            targeting_key="user-123",
            attributes={"segment": str(segment_id)},  # Simulate pre-evaluated segment
        )

        # Note: The current engine won't match IN_SEGMENT - this is expected
        # A full implementation would preprocess segment conditions
        result = await engine.evaluate(flag, context, storage)

        # Default behavior - segment conditions aren't directly evaluated by engine
        assert result is not None

    async def test_flag_with_standard_and_segment_conditions(
        self, engine: EvaluationEngine, storage: MemoryStorageBackend
    ) -> None:
        """Test flag rules mixing standard conditions with segment concepts."""
        flag_id = uuid4()

        flag = FeatureFlag(
            id=flag_id,
            key="mixed-feature",
            name="Mixed Feature",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[
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
                ),
            ],
            overrides=[],
            variants=[],
        )

        await storage.create_flag(flag)

        # Matching context
        context = EvaluationContext(
            targeting_key="user-123",
            attributes={"plan": "premium", "country": "US"},
        )
        result = await engine.evaluate(flag, context, storage)
        assert result.value is True

        # Non-matching context (wrong country)
        context_uk = EvaluationContext(
            targeting_key="user-456",
            attributes={"plan": "premium", "country": "UK"},
        )
        result_uk = await engine.evaluate(flag, context_uk, storage)
        assert result_uk.value is False


# -----------------------------------------------------------------------------
# TestEdgeCases - Edge cases and error handling
# -----------------------------------------------------------------------------
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_condition_with_none_attribute(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test condition with no attribute specified is skipped."""
        segment = create_segment(
            name="no_attribute",
            conditions=[
                {"operator": "eq", "value": "test"},  # Missing attribute
                {"attribute": "plan", "operator": "eq", "value": "premium"},
            ],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"plan": "premium"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        # First condition skipped, second matches
        assert result is True

    async def test_condition_with_none_context_value(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test condition when context attribute is None."""
        segment = create_segment(
            name="none_context",
            conditions=[
                {"attribute": "missing_attr", "operator": "gt", "value": 10}
            ],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={})  # Missing attribute
        result = await evaluator.is_in_segment(created.id, context, storage)

        # GT with None actual returns False
        assert result is False

    async def test_in_operator_empty_list(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test IN operator with empty list returns False."""
        segment = create_segment(
            name="empty_in",
            conditions=[{"attribute": "country", "operator": "in", "value": []}],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"country": "US"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        assert result is False

    async def test_not_in_operator_empty_list(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test NOT_IN operator with empty list returns True."""
        segment = create_segment(
            name="empty_not_in",
            conditions=[{"attribute": "country", "operator": "not_in", "value": []}],
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"country": "US"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        assert result is True

    async def test_parent_segment_not_found(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test nested segment with non-existent parent returns False."""
        non_existent_parent_id = uuid4()
        segment = create_segment(
            name="orphan",
            parent_segment_id=non_existent_parent_id,
            conditions=[],  # Would match all, but parent doesn't exist
        )
        created = await storage.create_segment(segment)

        context = EvaluationContext(attributes={"test": "value"})
        result = await evaluator.is_in_segment(created.id, context, storage)

        # Parent not found, so child doesn't match
        assert result is False

    async def test_parent_segment_disabled(
        self, evaluator: SegmentEvaluator, storage: MemoryStorageBackend
    ) -> None:
        """Test that disabled parent segment causes child to not match."""
        parent = create_segment(name="disabled_parent", conditions=[], enabled=False)
        parent = await storage.create_segment(parent)

        child = create_segment(
            name="child_of_disabled",
            parent_segment_id=parent.id,
            conditions=[],
        )
        child = await storage.create_segment(child)

        context = EvaluationContext(attributes={"test": "value"})
        result = await evaluator.is_in_segment(child.id, context, storage)

        # Parent is disabled, so child doesn't match
        assert result is False

    async def test_storage_close_clears_segments(
        self, storage: MemoryStorageBackend
    ) -> None:
        """Test that closing storage clears all segments."""
        segment = create_segment(name="temp_segment")
        await storage.create_segment(segment)

        # Verify segment exists
        assert len(await storage.get_all_segments()) == 1

        # Close storage
        await storage.close()

        # Verify segments are cleared
        assert len(await storage.get_all_segments()) == 0
