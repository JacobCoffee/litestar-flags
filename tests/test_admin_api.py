"""Comprehensive tests for the Admin API endpoints.

This module provides comprehensive test coverage for all Admin API controllers
including flags, rules, segments, environments, and permission guards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from litestar_flags import FeatureFlagsConfig, FeatureFlagsPlugin
from litestar_flags.admin import FeatureFlagsAdminConfig, FeatureFlagsAdminPlugin
from litestar_flags.admin.guards import Permission, Role
from litestar_flags.models.environment import Environment
from litestar_flags.models.flag import FeatureFlag
from litestar_flags.models.rule import FlagRule
from litestar_flags.models.segment import Segment
from litestar_flags.storage.memory import MemoryStorageBackend
from litestar_flags.types import FlagStatus, FlagType

if TYPE_CHECKING:
    from collections.abc import Generator


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockUser:
    """Mock user for testing authentication and authorization."""

    id: str
    roles: list[Role]
    permissions: list[Permission] | None = None


@pytest.fixture
def storage() -> MemoryStorageBackend:
    """Create a fresh memory storage backend for each test.

    Note: This storage is separate from the app's storage. Tests that need
    to use this storage should use the `client_with_storage` fixture instead.
    """
    return MemoryStorageBackend()


@pytest.fixture
def admin_user() -> MockUser:
    """Create a mock admin user with full permissions."""
    return MockUser(
        id="admin-user-1",
        roles=[Role.ADMIN],
        permissions=None,
    )


@pytest.fixture
def editor_user() -> MockUser:
    """Create a mock editor user."""
    return MockUser(
        id="editor-user-1",
        roles=[Role.EDITOR],
        permissions=None,
    )


@pytest.fixture
def viewer_user() -> MockUser:
    """Create a mock viewer user with read-only permissions."""
    return MockUser(
        id="viewer-user-1",
        roles=[Role.VIEWER],
        permissions=None,
    )


@pytest.fixture
def app_with_admin(admin_user: MockUser) -> Litestar:
    """Create a Litestar app with Admin API and admin user authentication."""
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler

    async def auth_guard(
        connection: ASGIConnection[Any, Any, Any, Any],
        _: BaseRouteHandler,
    ) -> None:
        """Set the admin user in the connection state."""
        connection.state.user = admin_user

    feature_flags_config = FeatureFlagsConfig(backend="memory")
    feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

    admin_config = FeatureFlagsAdminConfig(
        require_auth=True,
        auth_guard=auth_guard,
    )
    admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

    app = Litestar(
        route_handlers=[],
        plugins=[feature_flags_plugin, admin_plugin],
        debug=True,
    )

    return app


@pytest.fixture
def client(app_with_admin: Litestar) -> Generator[TestClient, None, None]:
    """Create a test client for the admin app.

    The storage backend is accessible via client.app.state.feature_flags_storage
    AFTER this fixture is created (when startup hooks have run).
    """
    with TestClient(app=app_with_admin) as test_client:
        yield test_client


def get_app_storage(app: Litestar) -> MemoryStorageBackend:
    """Get the storage backend from the app state.

    Helper function to get the storage backend after app startup.
    """
    return app.state.feature_flags_storage  # type: ignore[return-value]


def get_client_storage(client: TestClient) -> MemoryStorageBackend:
    """Get the storage backend from the test client's app state.

    Helper function to get the storage backend after app startup.
    """
    return client.app.state.feature_flags_storage  # type: ignore[return-value]


def create_sample_flag(storage: MemoryStorageBackend) -> FeatureFlag:
    """Create and store a sample flag in the given storage."""
    flag = FeatureFlag(
        id=uuid4(),
        key="test-feature",
        name="Test Feature",
        description="A test feature flag",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["test", "sample"],
        metadata_={},
        rules=[],
        overrides=[],
        variants=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    # Store synchronously for fixture setup
    storage._flags[flag.key] = flag
    storage._flags_by_id[flag.id] = flag
    return flag


@pytest.fixture
def sample_flag(client: TestClient) -> FeatureFlag:
    """Create and store a sample flag in the app's storage for testing."""
    storage = get_client_storage(client)
    return create_sample_flag(storage)


def create_sample_flag_with_rules(storage: MemoryStorageBackend) -> FeatureFlag:
    """Create and store a sample flag with rules in the given storage."""
    flag_id = uuid4()
    flag = FeatureFlag(
        id=flag_id,
        key="rules-test-feature",
        name="Rules Test Feature",
        description="A feature flag with rules",
        flag_type=FlagType.BOOLEAN,
        status=FlagStatus.ACTIVE,
        default_enabled=False,
        tags=["test"],
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
            FlagRule(
                id=uuid4(),
                flag_id=flag_id,
                name="Beta Users",
                priority=1,
                enabled=True,
                conditions=[{"attribute": "beta_tester", "operator": "eq", "value": True}],
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
    storage._flags[flag.key] = flag
    storage._flags_by_id[flag.id] = flag
    return flag


@pytest.fixture
def sample_flag_with_rules(client: TestClient) -> FeatureFlag:
    """Create and store a sample flag with rules in the app's storage for testing."""
    storage = get_client_storage(client)
    return create_sample_flag_with_rules(storage)


def create_sample_segment(storage: MemoryStorageBackend) -> Segment:
    """Create and store a sample segment in the given storage."""
    segment = Segment(
        id=uuid4(),
        name="premium_users",
        description="Premium plan subscribers",
        conditions=[{"attribute": "plan", "operator": "eq", "value": "premium"}],
        parent_segment_id=None,
        enabled=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    storage._segments[segment.id] = segment
    storage._segments_by_name[segment.name] = segment
    return segment


@pytest.fixture
def sample_segment(client: TestClient) -> Segment:
    """Create and store a sample segment in the app's storage for testing."""
    storage = get_client_storage(client)
    return create_sample_segment(storage)


def create_sample_environment(storage: MemoryStorageBackend) -> Environment:
    """Create and store a sample environment in the given storage."""
    env = Environment(
        id=uuid4(),
        name="Staging",
        slug="staging",
        description="Staging environment for testing",
        parent_id=None,
        is_active=True,
        settings={"debug": True},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    storage._environments[env.slug] = env
    storage._environments_by_id[env.id] = env
    return env


@pytest.fixture
def sample_environment(client: TestClient) -> Environment:
    """Create and store a sample environment in the app's storage for testing."""
    storage = get_client_storage(client)
    return create_sample_environment(storage)


# =============================================================================
# FlagsController Tests
# =============================================================================


class TestFlagsController:
    """Tests for the FlagsController CRUD operations."""

    def test_list_flags_empty(self, client: TestClient) -> None:
        """Test listing flags when none exist."""
        response = client.get("/admin/flags/")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 1

    def test_list_flags(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test listing flags returns existing flags."""
        response = client.get("/admin/flags/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["key"] == "test-feature"
        assert data["items"][0]["name"] == "Test Feature"

    def test_list_flags_with_pagination(
        self,
        client: TestClient,
    ) -> None:
        """Test pagination when listing flags."""
        # Get the app's storage
        storage = get_client_storage(client)

        # Create multiple flags
        for i in range(25):
            flag = FeatureFlag(
                id=uuid4(),
                key=f"flag-{i:03d}",
                name=f"Flag {i}",
                flag_type=FlagType.BOOLEAN,
                status=FlagStatus.ACTIVE,
                default_enabled=False,
                tags=[],
                metadata_={},
                rules=[],
                overrides=[],
                variants=[],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            storage._flags[flag.key] = flag
            storage._flags_by_id[flag.id] = flag

        # Test first page
        response = client.get("/admin/flags/?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 3

        # Test second page
        response = client.get("/admin/flags/?page=2&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 2

        # Test last page
        response = client.get("/admin/flags/?page=3&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 3

    def test_list_flags_filter_by_status(
        self,
        client: TestClient,
    ) -> None:
        """Test filtering flags by status."""
        # Get the app's storage
        storage = get_client_storage(client)

        # Create an active flag
        active_flag = FeatureFlag(
            id=uuid4(),
            key="active-flag",
            name="Active Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ACTIVE,
            default_enabled=True,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        storage._flags[active_flag.key] = active_flag
        storage._flags_by_id[active_flag.id] = active_flag

        # Filter by ACTIVE status (use lowercase for enum value)
        response = client.get("/admin/flags/?status=active")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["key"] == "active-flag"
        assert data["items"][0]["status"] == "active"

    def test_get_flag_by_id(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test getting a flag by its UUID."""
        response = client.get(f"/admin/flags/{sample_flag.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(sample_flag.id)
        assert data["key"] == "test-feature"
        assert data["name"] == "Test Feature"
        assert data["description"] == "A test feature flag"
        assert data["flag_type"] == "boolean"
        assert data["status"] == "active"
        assert data["default_enabled"] is False
        assert "test" in data["tags"]

    def test_get_flag_not_found(self, client: TestClient) -> None:
        """Test 404 response when flag not found."""
        fake_id = uuid4()
        response = client.get(f"/admin/flags/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_flag_by_key(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test getting a flag by its key."""
        response = client.get("/admin/flags/by-key/test-feature")
        assert response.status_code == 200

        data = response.json()
        assert data["key"] == "test-feature"
        assert data["name"] == "Test Feature"

    def test_get_flag_by_key_not_found(self, client: TestClient) -> None:
        """Test 404 response when flag key not found."""
        response = client.get("/admin/flags/by-key/nonexistent-flag")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_flag(self, client: TestClient) -> None:
        """Test creating a new flag."""
        payload = {
            "key": "new-feature",
            "name": "New Feature",
            "description": "A brand new feature",
            "flag_type": "boolean",
            "default_enabled": True,
            "tags": ["new", "beta"],
            "metadata": {"owner": "team-a"},
        }

        response = client.post("/admin/flags/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["key"] == "new-feature"
        assert data["name"] == "New Feature"
        assert data["description"] == "A brand new feature"
        assert data["flag_type"] == "boolean"
        assert data["status"] == "active"  # Default status
        assert data["default_enabled"] is True
        assert "new" in data["tags"]
        assert "beta" in data["tags"]
        assert data["metadata"]["owner"] == "team-a"
        assert "id" in data
        assert "created_at" in data

    def test_create_flag_minimal(self, client: TestClient) -> None:
        """Test creating a flag with minimal required fields."""
        payload = {
            "key": "minimal-feature",
            "name": "Minimal Feature",
        }

        response = client.post("/admin/flags/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["key"] == "minimal-feature"
        assert data["name"] == "Minimal Feature"
        assert data["flag_type"] == "boolean"  # Default
        assert data["default_enabled"] is False  # Default

    def test_create_flag_duplicate_key(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test 409 conflict when creating flag with duplicate key."""
        payload = {
            "key": "test-feature",  # Same as sample_flag
            "name": "Duplicate Feature",
        }

        response = client.post("/admin/flags/", json=payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_update_flag_full(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test full update (PUT) of a flag."""
        payload = {
            "name": "Updated Test Feature",
            "description": "Updated description",
            "flag_type": "boolean",
            "status": "active",
            "default_enabled": True,
            "tags": ["updated"],
            "metadata": {"version": 2},
        }

        response = client.put(f"/admin/flags/{sample_flag.id}", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Test Feature"
        assert data["description"] == "Updated description"
        assert data["default_enabled"] is True
        assert data["tags"] == ["updated"]
        assert data["metadata"]["version"] == 2

    def test_patch_flag(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test partial update (PATCH) of a flag."""
        payload = {
            "default_enabled": True,
        }

        response = client.patch(f"/admin/flags/{sample_flag.id}", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["default_enabled"] is True
        # Other fields should remain unchanged
        assert data["name"] == "Test Feature"
        assert data["description"] == "A test feature flag"

    def test_delete_flag(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test deleting a flag."""
        response = client.delete(f"/admin/flags/{sample_flag.id}")
        assert response.status_code == 204

        # Verify flag is deleted
        response = client.get(f"/admin/flags/{sample_flag.id}")
        assert response.status_code == 404

    def test_delete_flag_not_found(self, client: TestClient) -> None:
        """Test 404 when deleting non-existent flag."""
        fake_id = uuid4()
        response = client.delete(f"/admin/flags/{fake_id}")
        assert response.status_code == 404

    def test_archive_flag(self, client: TestClient, sample_flag: FeatureFlag) -> None:
        """Test archiving a flag."""
        response = client.post(f"/admin/flags/{sample_flag.id}/archive")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "archived"

    def test_archive_already_archived_flag(
        self,
        client: TestClient,
    ) -> None:
        """Test 409 conflict when archiving already archived flag."""
        # Get the app's storage
        storage = get_client_storage(client)

        # Create an already archived flag
        archived_flag = FeatureFlag(
            id=uuid4(),
            key="archived-flag",
            name="Archived Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ARCHIVED,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        storage._flags[archived_flag.key] = archived_flag
        storage._flags_by_id[archived_flag.id] = archived_flag

        response = client.post(f"/admin/flags/{archived_flag.id}/archive")
        assert response.status_code == 409
        assert "already archived" in response.json()["detail"].lower()

    def test_restore_flag(
        self,
        client: TestClient,
    ) -> None:
        """Test restoring an archived flag."""
        # Get the app's storage
        storage = get_client_storage(client)

        # Create an archived flag
        archived_flag = FeatureFlag(
            id=uuid4(),
            key="to-restore-flag",
            name="To Restore Flag",
            flag_type=FlagType.BOOLEAN,
            status=FlagStatus.ARCHIVED,
            default_enabled=False,
            tags=[],
            metadata_={},
            rules=[],
            overrides=[],
            variants=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        storage._flags[archived_flag.key] = archived_flag
        storage._flags_by_id[archived_flag.id] = archived_flag

        response = client.post(f"/admin/flags/{archived_flag.id}/restore")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "active"

    def test_restore_non_archived_flag(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test 409 conflict when restoring non-archived flag."""
        response = client.post(f"/admin/flags/{sample_flag.id}/restore")
        assert response.status_code == 409
        assert "not archived" in response.json()["detail"].lower()


# =============================================================================
# RulesController Tests
# =============================================================================


class TestRulesController:
    """Tests for the RulesController CRUD operations."""

    def test_list_rules_for_flag(
        self,
        client: TestClient,
        sample_flag_with_rules: FeatureFlag,
    ) -> None:
        """Test listing rules for a flag."""
        response = client.get(f"/admin/flags/{sample_flag_with_rules.id}/rules/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Rules should be sorted by priority
        assert data["items"][0]["name"] == "Premium Users"
        assert data["items"][0]["priority"] == 0
        assert data["items"][1]["name"] == "Beta Users"
        assert data["items"][1]["priority"] == 1

    def test_list_rules_empty(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test listing rules when flag has no rules."""
        response = client.get(f"/admin/flags/{sample_flag.id}/rules/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_rules_flag_not_found(self, client: TestClient) -> None:
        """Test 404 when listing rules for non-existent flag."""
        fake_id = uuid4()
        response = client.get(f"/admin/flags/{fake_id}/rules/")
        assert response.status_code == 404

    def test_create_rule(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test creating a rule for a flag."""
        payload = {
            "name": "New Rule",
            "description": "A new targeting rule",
            "priority": 0,
            "enabled": True,
            "conditions": [
                {"attribute": "country", "operator": "in", "value": ["US", "CA"]},
            ],
            "serve_enabled": True,
            "rollout_percentage": 50,
        }

        response = client.post(
            f"/admin/flags/{sample_flag.id}/rules/",
            json=payload,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "New Rule"
        assert data["description"] == "A new targeting rule"
        assert data["priority"] == 0
        assert data["enabled"] is True
        assert len(data["conditions"]) == 1
        assert data["serve_enabled"] is True
        assert data["rollout_percentage"] == 50

    def test_create_rule_invalid_conditions(
        self,
        client: TestClient,
        sample_flag: FeatureFlag,
    ) -> None:
        """Test validation error for invalid conditions."""
        payload = {
            "name": "Invalid Rule",
            "conditions": [
                {"attribute": "country"},  # Missing operator and value
            ],
            "serve_enabled": True,
        }

        response = client.post(
            f"/admin/flags/{sample_flag.id}/rules/",
            json=payload,
        )
        assert response.status_code == 400

    def test_update_rule(
        self,
        client: TestClient,
        sample_flag_with_rules: FeatureFlag,
    ) -> None:
        """Test updating a rule."""
        rule_id = sample_flag_with_rules.rules[0].id

        payload = {
            "name": "Updated Premium Users",
            "description": "Updated description",
            "priority": 0,
            "enabled": True,
            "conditions": [
                {"attribute": "plan", "operator": "eq", "value": "enterprise"},
            ],
            "serve_enabled": True,
        }

        response = client.put(
            f"/admin/flags/{sample_flag_with_rules.id}/rules/{rule_id}",
            json=payload,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Premium Users"
        assert data["conditions"][0]["value"] == "enterprise"

    def test_delete_rule(
        self,
        client: TestClient,
        sample_flag_with_rules: FeatureFlag,
    ) -> None:
        """Test deleting a rule."""
        rule_id = sample_flag_with_rules.rules[0].id

        response = client.delete(
            f"/admin/flags/{sample_flag_with_rules.id}/rules/{rule_id}"
        )
        assert response.status_code == 204

        # Verify rule is deleted
        response = client.get(f"/admin/flags/{sample_flag_with_rules.id}/rules/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Beta Users"

    def test_reorder_rules(
        self,
        client: TestClient,
        sample_flag_with_rules: FeatureFlag,
    ) -> None:
        """Test reordering rules by priority."""
        rule_ids = [str(rule.id) for rule in sample_flag_with_rules.rules]
        # Reverse the order
        reversed_ids = list(reversed(rule_ids))

        payload = {"rule_ids": reversed_ids}

        response = client.post(
            f"/admin/flags/{sample_flag_with_rules.id}/rules/reorder",
            json=payload,
        )
        assert response.status_code == 200

        data = response.json()
        # Check that order is reversed
        assert data[0]["name"] == "Beta Users"
        assert data[0]["priority"] == 0
        assert data[1]["name"] == "Premium Users"
        assert data[1]["priority"] == 1


# =============================================================================
# SegmentsController Tests
# =============================================================================


class TestSegmentsController:
    """Tests for the SegmentsController CRUD operations."""

    def test_list_segments_empty(self, client: TestClient) -> None:
        """Test listing segments when none exist."""
        response = client.get("/admin/segments/")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_segments(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test listing segments returns existing segments."""
        response = client.get("/admin/segments/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "premium_users"
        assert data["items"][0]["enabled"] is True

    def test_create_segment(self, client: TestClient) -> None:
        """Test creating a new segment."""
        payload = {
            "name": "enterprise_users",
            "description": "Enterprise plan subscribers",
            "conditions": [
                {"attribute": "plan", "operator": "eq", "value": "enterprise"},
            ],
            "enabled": True,
        }

        response = client.post("/admin/segments/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "enterprise_users"
        assert data["description"] == "Enterprise plan subscribers"
        assert data["enabled"] is True
        assert len(data["conditions"]) == 1

    def test_create_segment_duplicate_name(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test 409 conflict when creating segment with duplicate name."""
        payload = {
            "name": "premium_users",  # Same as sample_segment
            "conditions": [],
        }

        response = client.post("/admin/segments/", json=payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_get_segment_by_id(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test getting a segment by ID."""
        response = client.get(f"/admin/segments/{sample_segment.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(sample_segment.id)
        assert data["name"] == "premium_users"

    def test_get_segment_by_name(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test getting a segment by name."""
        response = client.get("/admin/segments/by-name/premium_users")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "premium_users"

    def test_evaluate_segment_matches(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test segment evaluation that matches."""
        payload = {
            "context": {"plan": "premium"},
        }

        response = client.post(
            f"/admin/segments/{sample_segment.id}/evaluate",
            json=payload,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["matches"] is True
        assert data["segment_name"] == "premium_users"
        assert len(data["matched_conditions"]) == 1
        assert len(data["failed_conditions"]) == 0

    def test_evaluate_segment_no_match(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test segment evaluation that does not match."""
        payload = {
            "context": {"plan": "free"},
        }

        response = client.post(
            f"/admin/segments/{sample_segment.id}/evaluate",
            json=payload,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["matches"] is False
        assert len(data["matched_conditions"]) == 0
        assert len(data["failed_conditions"]) == 1

    def test_delete_segment(
        self,
        client: TestClient,
        sample_segment: Segment,
    ) -> None:
        """Test deleting a segment."""
        response = client.delete(f"/admin/segments/{sample_segment.id}")
        assert response.status_code == 204

        # Verify segment is deleted
        response = client.get(f"/admin/segments/{sample_segment.id}")
        assert response.status_code == 404


# =============================================================================
# EnvironmentsController Tests
# =============================================================================


class TestEnvironmentsController:
    """Tests for the EnvironmentsController CRUD operations."""

    def test_list_environments_empty(self, client: TestClient) -> None:
        """Test listing environments when none exist."""
        response = client.get("/admin/environments/")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_environments(
        self,
        client: TestClient,
        sample_environment: Environment,
    ) -> None:
        """Test listing environments returns existing environments."""
        response = client.get("/admin/environments/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["slug"] == "staging"
        assert data["items"][0]["name"] == "Staging"

    def test_create_environment(self, client: TestClient) -> None:
        """Test creating a new environment."""
        payload = {
            "name": "Production",
            "slug": "production",
            "description": "Production environment",
            "is_production": True,
            "color": "#FF0000",
            "settings": {"require_approval": True},
        }

        response = client.post("/admin/environments/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Production"
        assert data["slug"] == "production"
        assert data["is_active"] is True

    def test_create_environment_invalid_slug(self, client: TestClient) -> None:
        """Test validation error for invalid slug format."""
        payload = {
            "name": "Invalid Env",
            "slug": "Invalid Slug With Spaces",  # Invalid
        }

        response = client.post("/admin/environments/", json=payload)
        assert response.status_code == 400
        assert "invalid slug format" in response.json()["detail"].lower()

    def test_create_environment_duplicate_slug(
        self,
        client: TestClient,
        sample_environment: Environment,
    ) -> None:
        """Test 409 conflict when creating environment with duplicate slug."""
        payload = {
            "name": "Another Staging",
            "slug": "staging",  # Same as sample_environment
        }

        response = client.post("/admin/environments/", json=payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_get_environment_by_id(
        self,
        client: TestClient,
        sample_environment: Environment,
    ) -> None:
        """Test getting an environment by ID."""
        response = client.get(f"/admin/environments/{sample_environment.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["slug"] == "staging"
        assert data["name"] == "Staging"

    def test_get_environment_by_slug(
        self,
        client: TestClient,
        sample_environment: Environment,
    ) -> None:
        """Test getting an environment by slug."""
        response = client.get("/admin/environments/by-slug/staging")
        assert response.status_code == 200

        data = response.json()
        assert data["slug"] == "staging"

    def test_delete_environment(
        self,
        client: TestClient,
        sample_environment: Environment,
    ) -> None:
        """Test deleting an environment."""
        response = client.delete(f"/admin/environments/{sample_environment.id}")
        assert response.status_code == 204

        # Verify environment is deleted
        response = client.get(f"/admin/environments/{sample_environment.id}")
        assert response.status_code == 404

    @pytest.mark.skip(
        reason="Environment model does not have is_production field yet"
    )
    def test_delete_production_environment_blocked(
        self,
        client: TestClient,
    ) -> None:
        """Test that deleting production environment requires force flag.

        NOTE: This test is skipped because the Environment model doesn't have
        an is_production field. When that feature is implemented, this test
        should be enabled.
        """
        # Get the app's storage
        storage = get_client_storage(client)

        # Create a production environment
        prod_env = Environment(
            id=uuid4(),
            name="Production",
            slug="production",
            description="Production environment",
            parent_id=None,
            is_active=True,
            settings={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        if hasattr(prod_env, "is_production"):
            prod_env.is_production = True  # type: ignore[misc]

        storage._environments[prod_env.slug] = prod_env
        storage._environments_by_id[prod_env.id] = prod_env

        # Try to delete without force flag
        response = client.delete(f"/admin/environments/{prod_env.id}")
        assert response.status_code == 400
        assert "force" in response.json()["detail"].lower()

        # Delete with force flag
        response = client.delete(f"/admin/environments/{prod_env.id}?force=true")
        assert response.status_code == 204


# =============================================================================
# Permission Guard Tests
# =============================================================================


class TestPermissionGuards:
    """Tests for permission-based access control."""

    def test_permission_denied_without_auth(self) -> None:
        """Test that requests without authentication are denied."""
        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(require_auth=True)  # No auth_guard set
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            response = client.get("/admin/flags/")
            # Should be denied because no user is set
            assert response.status_code == 403

    def test_permission_granted_with_role(self) -> None:
        """Test that requests with correct role are allowed."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        viewer_user = MockUser(id="viewer-1", roles=[Role.VIEWER])

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = viewer_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            require_auth=True,
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Viewer can read flags
            response = client.get("/admin/flags/")
            assert response.status_code == 200

    def test_permission_denied_for_write_with_viewer(self) -> None:
        """Test that viewer cannot write flags."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        viewer_user = MockUser(id="viewer-1", roles=[Role.VIEWER])

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = viewer_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            require_auth=True,
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Viewer cannot create flags
            response = client.post(
                "/admin/flags/",
                json={"key": "new-flag", "name": "New Flag"},
            )
            assert response.status_code == 403
            assert "permission" in response.json()["detail"].lower()

    def test_editor_can_write_but_not_delete(self) -> None:
        """Test that editor can write but not delete flags."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        editor_user = MockUser(id="editor-1", roles=[Role.EDITOR])

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = editor_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            require_auth=True,
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Editor can create flags
            response = client.post(
                "/admin/flags/",
                json={"key": "editor-flag", "name": "Editor Flag"},
            )
            assert response.status_code == 201

            flag_id = response.json()["id"]

            # Editor cannot delete flags
            response = client.delete(f"/admin/flags/{flag_id}")
            assert response.status_code == 403

    def test_admin_has_full_access(self) -> None:
        """Test that admin has full CRUD access."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        admin_user = MockUser(id="admin-1", roles=[Role.ADMIN])

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = admin_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            require_auth=True,
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Admin can read
            response = client.get("/admin/flags/")
            assert response.status_code == 200

            # Admin can create
            response = client.post(
                "/admin/flags/",
                json={"key": "admin-flag", "name": "Admin Flag"},
            )
            assert response.status_code == 201
            flag_id = response.json()["id"]

            # Admin can update
            response = client.patch(
                f"/admin/flags/{flag_id}",
                json={"name": "Updated Admin Flag"},
            )
            assert response.status_code == 200

            # Admin can delete
            response = client.delete(f"/admin/flags/{flag_id}")
            assert response.status_code == 204


# =============================================================================
# FeatureFlagsAdminPlugin Configuration Tests
# =============================================================================


class TestFeatureFlagsAdminPluginConfiguration:
    """Tests for FeatureFlagsAdminPlugin configuration options."""

    def test_admin_plugin_disabled(self, storage: MemoryStorageBackend) -> None:
        """Test that disabled admin plugin does not register routes."""
        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(enabled=False)
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            response = client.get("/admin/flags/")
            assert response.status_code == 404

    def test_admin_plugin_custom_path_prefix(
        self,
        storage: MemoryStorageBackend,
        admin_user: MockUser,
    ) -> None:
        """Test custom path prefix for admin routes."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = admin_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            path_prefix="/api/v1",
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Original path should not work
            response = client.get("/admin/flags/")
            assert response.status_code == 404

            # Prefixed path should work
            response = client.get("/api/v1/admin/flags/")
            assert response.status_code == 200

    def test_admin_plugin_selective_controllers(
        self,
        storage: MemoryStorageBackend,
        admin_user: MockUser,
    ) -> None:
        """Test enabling only specific controllers."""
        from litestar.connection import ASGIConnection
        from litestar.handlers.base import BaseRouteHandler

        async def auth_guard(
            connection: ASGIConnection[Any, Any, Any, Any],
            _: BaseRouteHandler,
        ) -> None:
            connection.state.user = admin_user

        feature_flags_config = FeatureFlagsConfig(backend="memory")
        feature_flags_plugin = FeatureFlagsPlugin(config=feature_flags_config)

        admin_config = FeatureFlagsAdminConfig(
            enable_flags=True,
            enable_rules=False,
            enable_segments=False,
            enable_environments=False,
            enable_analytics=False,
            enable_overrides=False,
            auth_guard=auth_guard,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        app = Litestar(
            route_handlers=[],
            plugins=[feature_flags_plugin, admin_plugin],
            debug=True,
        )

        with TestClient(app) as client:
            # Flags endpoint should work
            response = client.get("/admin/flags/")
            assert response.status_code == 200

            # Segments endpoint should not exist
            response = client.get("/admin/segments/")
            assert response.status_code == 404

            # Environments endpoint should not exist
            response = client.get("/admin/environments/")
            assert response.status_code == 404

    def test_get_enabled_controllers(self) -> None:
        """Test getting list of enabled controllers."""
        admin_config = FeatureFlagsAdminConfig(
            enable_flags=True,
            enable_rules=True,
            enable_segments=False,
            enable_environments=True,
            enable_analytics=False,
            enable_overrides=False,
        )
        admin_plugin = FeatureFlagsAdminPlugin(config=admin_config)

        enabled = admin_plugin.get_enabled_controllers()
        assert "FlagsController" in enabled
        assert "RulesController" in enabled
        assert "EnvironmentsController" in enabled
        assert "SegmentsController" not in enabled
        assert "AnalyticsController" not in enabled
        assert "OverridesController" not in enabled
