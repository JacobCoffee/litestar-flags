"""Database Backend Example.

This example demonstrates using litestar-flags with a database backend:
- Setting up DatabaseStorageBackend with Advanced-Alchemy
- Creating and configuring an async SQLAlchemy session
- CRUD operations on feature flags
- Using the database backend with Litestar

Prerequisites:
    pip install litestar-flags[database]
    # For PostgreSQL: pip install asyncpg
    # For SQLite: pip install aiosqlite

To run this example with SQLite:
    uvicorn examples.database_backend:app --reload

For PostgreSQL, set the DATABASE_URL environment variable:
    export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/mydb"
    uvicorn examples.database_backend:app --reload
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from litestar import Litestar, delete, get, post, put
from litestar.exceptions import NotFoundException

from litestar_flags import (
    EvaluationContext,
    FeatureFlag,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    FlagStatus,
    FlagType,
)

if TYPE_CHECKING:
    from litestar.datastructures import State


# Get database URL from environment or use SQLite for development
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./feature_flags.db",
)

# Create plugin configuration with database backend
config = FeatureFlagsConfig(
    backend="database",
    connection_string=DATABASE_URL,
    table_prefix="ff_",  # Optional: prefix for database tables
)


async def seed_database(state: State) -> None:
    """Seed the database with initial feature flags.

    This runs on application startup and creates sample flags
    if they don't already exist.
    """
    # Import the storage backend to access CRUD methods
    from litestar_flags.storage.database import DatabaseStorageBackend

    storage: DatabaseStorageBackend = state.feature_flags_storage

    # Check if flags already exist
    existing = await storage.get_flag("db_feature_1")
    if existing:
        print("Database already seeded, skipping...")
        return

    # Create sample flags
    flags_to_create = [
        FeatureFlag(
            key="db_feature_1",
            name="Database Feature 1",
            description="A feature flag stored in the database",
            flag_type=FlagType.BOOLEAN,
            default_enabled=True,
            tags=["database", "example"],
        ),
        FeatureFlag(
            key="db_feature_2",
            name="Database Feature 2",
            description="Another database-backed feature flag",
            flag_type=FlagType.BOOLEAN,
            default_enabled=False,
            tags=["database", "example"],
        ),
        FeatureFlag(
            key="config_value",
            name="Configuration Value",
            description="A JSON configuration flag",
            flag_type=FlagType.JSON,
            default_value={
                "max_items": 100,
                "timeout_seconds": 30,
                "features": ["basic", "advanced"],
            },
            tags=["config"],
        ),
    ]

    for flag in flags_to_create:
        await storage.create_flag(flag)
        print(f"Created flag: {flag.key}")

    print("Database seeded successfully!")


# Route Handlers


@get("/")
async def index() -> dict:
    """List available API endpoints."""
    return {
        "message": "Database Backend Example",
        "endpoints": {
            "GET /flags": "List all active flags",
            "GET /flags/{key}": "Get a specific flag",
            "POST /flags": "Create a new flag",
            "PUT /flags/{key}": "Update a flag",
            "DELETE /flags/{key}": "Delete a flag",
            "GET /evaluate/{key}": "Evaluate a flag",
        },
    }


@get("/flags")
async def list_flags(feature_flags: FeatureFlagClient) -> dict:
    """List all active feature flags.

    Demonstrates retrieving all flags from the database backend.
    """
    all_flags = await feature_flags.storage.get_all_active_flags()

    return {
        "flags": [
            {
                "key": flag.key,
                "name": flag.name,
                "description": flag.description,
                "type": flag.flag_type.value,
                "status": flag.status.value,
                "default_enabled": flag.default_enabled,
                "tags": flag.tags,
            }
            for flag in all_flags
        ],
        "total": len(all_flags),
    }


@get("/flags/{flag_key:str}")
async def get_flag(
    flag_key: str,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Get a specific flag by key.

    Demonstrates retrieving a single flag from storage.

    Args:
        flag_key: The unique flag key
        feature_flags: Injected feature flag client

    Returns:
        Flag details or 404 if not found

    """
    flag = await feature_flags.storage.get_flag(flag_key)

    if flag is None:
        raise NotFoundException(f"Flag '{flag_key}' not found")

    return {
        "key": flag.key,
        "name": flag.name,
        "description": flag.description,
        "type": flag.flag_type.value,
        "status": flag.status.value,
        "default_enabled": flag.default_enabled,
        "default_value": flag.default_value,
        "tags": flag.tags,
        "created_at": str(flag.created_at) if flag.created_at else None,
        "updated_at": str(flag.updated_at) if flag.updated_at else None,
    }


@post("/flags")
async def create_flag(
    data: dict,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Create a new feature flag.

    Demonstrates creating flags via the storage backend.

    Expected request body:
        {
            "key": "new_feature",
            "name": "New Feature",
            "description": "Description of the feature",
            "type": "boolean",
            "default_enabled": false,
            "tags": ["new", "feature"]
        }

    Args:
        data: Request body with flag data
        feature_flags: Injected feature flag client

    Returns:
        Created flag details

    """
    # Parse flag type
    flag_type_str = data.get("type", "boolean")
    try:
        flag_type = FlagType(flag_type_str)
    except ValueError:
        flag_type = FlagType.BOOLEAN

    # Create the flag object
    flag = FeatureFlag(
        key=data["key"],
        name=data.get("name", data["key"]),
        description=data.get("description"),
        flag_type=flag_type,
        default_enabled=data.get("default_enabled", False),
        default_value=data.get("default_value"),
        tags=data.get("tags", []),
    )

    # Save to database
    created = await feature_flags.storage.create_flag(flag)

    return {
        "message": "Flag created successfully",
        "flag": {
            "key": created.key,
            "name": created.name,
            "type": created.flag_type.value,
            "default_enabled": created.default_enabled,
        },
    }


@put("/flags/{flag_key:str}")
async def update_flag(
    flag_key: str,
    data: dict,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Update an existing feature flag.

    Demonstrates updating flags in the database.

    Expected request body (all fields optional):
        {
            "name": "Updated Name",
            "description": "Updated description",
            "default_enabled": true,
            "status": "active",
            "tags": ["updated"]
        }

    Args:
        flag_key: The unique flag key
        data: Request body with update data
        feature_flags: Injected feature flag client

    Returns:
        Updated flag details

    """
    # Get existing flag
    flag = await feature_flags.storage.get_flag(flag_key)
    if flag is None:
        raise NotFoundException(f"Flag '{flag_key}' not found")

    # Update fields
    if "name" in data:
        flag.name = data["name"]
    if "description" in data:
        flag.description = data["description"]
    if "default_enabled" in data:
        flag.default_enabled = data["default_enabled"]
    if "default_value" in data:
        flag.default_value = data["default_value"]
    if "tags" in data:
        flag.tags = data["tags"]
    if "status" in data:
        try:
            flag.status = FlagStatus(data["status"])
        except ValueError:
            pass

    # Save updates
    updated = await feature_flags.storage.update_flag(flag)

    return {
        "message": "Flag updated successfully",
        "flag": {
            "key": updated.key,
            "name": updated.name,
            "status": updated.status.value,
            "default_enabled": updated.default_enabled,
        },
    }


@delete("/flags/{flag_key:str}", status_code=200)
async def delete_flag(
    flag_key: str,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Delete a feature flag.

    Demonstrates deleting flags from the database.

    Args:
        flag_key: The unique flag key
        feature_flags: Injected feature flag client

    Returns:
        Confirmation message

    """
    deleted = await feature_flags.storage.delete_flag(flag_key)

    if not deleted:
        raise NotFoundException(f"Flag '{flag_key}' not found")

    return {
        "message": f"Flag '{flag_key}' deleted successfully",
    }


@get("/evaluate/{flag_key:str}")
async def evaluate_flag(
    flag_key: str,
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> dict:
    """Evaluate a feature flag.

    Demonstrates evaluating flags with the database backend.

    Args:
        flag_key: The unique flag key
        feature_flags: Injected feature flag client
        user_id: Optional user ID for targeting

    Returns:
        Evaluation result with details

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Get evaluation with full details
    details = await feature_flags.get_boolean_details(
        flag_key,
        default=False,
        context=context,
    )

    return {
        "flag_key": details.flag_key,
        "value": details.value,
        "reason": details.reason.value,
        "variant": details.variant,
        "error": {
            "code": details.error_code.value if details.error_code else None,
            "message": details.error_message,
        }
        if details.error_code
        else None,
    }


# Create the Litestar application
app = Litestar(
    route_handlers=[
        index,
        list_flags,
        get_flag,
        create_flag,
        update_flag,
        delete_flag,
        evaluate_flag,
    ],
    plugins=[FeatureFlagsPlugin(config=config)],
    on_startup=[seed_database],
    debug=True,
)


# Standalone database operations demo
async def standalone_database_demo() -> None:
    """Demonstrate using DatabaseStorageBackend directly.

    This example shows how to use the database backend outside
    of a Litestar application context.
    """
    print("\n--- Standalone Database Demo ---\n")

    # Import the database backend
    try:
        from litestar_flags.storage.database import DatabaseStorageBackend
    except ImportError:
        print("Database backend not available. Install with:")
        print("  pip install litestar-flags[database]")
        return

    # Create the storage backend (uses SQLite for demo)
    storage = await DatabaseStorageBackend.create(
        connection_string="sqlite+aiosqlite:///./standalone_demo.db",
        create_tables=True,
    )

    try:
        # Create a flag
        flag = FeatureFlag(
            key="standalone_db_flag",
            name="Standalone DB Flag",
            description="Created via standalone script",
            flag_type=FlagType.BOOLEAN,
            default_enabled=True,
        )

        # Check if it already exists
        existing = await storage.get_flag(flag.key)
        if existing:
            print(f"Flag already exists: {existing.key}")
            flag = existing
        else:
            flag = await storage.create_flag(flag)
            print(f"Created flag: {flag.key}")

        # Use the client for evaluation
        client = FeatureFlagClient(storage=storage)

        context = EvaluationContext(targeting_key="user-456")
        is_enabled = await client.is_enabled("standalone_db_flag", context=context)
        print(f"Flag is enabled: {is_enabled}")

        # List all active flags
        all_flags = await storage.get_all_active_flags()
        print(f"\nTotal active flags: {len(all_flags)}")
        for f in all_flags:
            print(f"  - {f.key}: {f.name}")

        # Update the flag
        flag.description = "Updated description"
        updated = await storage.update_flag(flag)
        print(f"\nUpdated flag description: {updated.description}")

        # Health check
        is_healthy = await storage.health_check()
        print(f"\nStorage health: {'OK' if is_healthy else 'FAIL'}")

    finally:
        # Clean up
        await storage.close()
        print("\nDatabase connection closed")


if __name__ == "__main__":
    asyncio.run(standalone_database_demo())
