"""Decorator Usage Example.

This example demonstrates using litestar-flags decorators:
- @feature_flag: Conditionally execute route handlers
- @require_flag: Require a flag to be enabled (raises exception otherwise)
- Custom response handling for disabled features
- Integration with Litestar route handlers

Decorators provide a clean, declarative way to gate features
without cluttering your handler logic.

To run this example:
    uvicorn examples.decorators:app --reload

Then visit:
    - http://localhost:8000/
    - http://localhost:8000/new-feature
    - http://localhost:8000/beta
    - http://localhost:8000/premium
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from litestar import Litestar, Request, get
from litestar.exceptions import NotAuthorizedException
from litestar.response import Response

from litestar_flags import (
    EvaluationContext,
    FeatureFlag,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    FlagRule,
    FlagType,
    MemoryStorageBackend,
    feature_flag,
    require_flag,
)

if TYPE_CHECKING:
    from litestar.datastructures import State


config = FeatureFlagsConfig(backend="memory")


async def setup_decorator_flags(state: State) -> None:
    """Set up feature flags for decorator examples.

    Creates flags that demonstrate different decorator use cases.
    """
    storage: MemoryStorageBackend = state.feature_flags_storage

    # Flag 1: Enabled feature (new_feature)
    # This flag is enabled for everyone
    new_feature_flag = FeatureFlag(
        key="new_feature",
        name="New Feature",
        description="A new feature that is fully rolled out",
        flag_type=FlagType.BOOLEAN,
        default_enabled=True,
    )
    await storage.create_flag(new_feature_flag)

    # Flag 2: Disabled feature (coming_soon)
    # This flag is disabled for everyone
    coming_soon_flag = FeatureFlag(
        key="coming_soon",
        name="Coming Soon Feature",
        description="A feature that is not yet available",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
    )
    await storage.create_flag(coming_soon_flag)

    # Flag 3: Beta access flag
    # Enabled only for users with beta_user attribute
    beta_flag = FeatureFlag(
        key="beta_access",
        name="Beta Access",
        description="Access to beta features",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            FlagRule(
                name="beta_users",
                description="Enable for beta users",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "is_beta_user", "operator": "eq", "value": True},
                ],
                serve_enabled=True,
            ),
        ],
    )
    await storage.create_flag(beta_flag)

    # Flag 4: Premium feature flag
    # Enabled for premium plan users
    premium_flag = FeatureFlag(
        key="premium_feature",
        name="Premium Feature",
        description="Feature available to premium subscribers",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            FlagRule(
                name="premium_users",
                description="Enable for premium users",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "plan", "operator": "in", "value": ["premium", "enterprise"]},
                ],
                serve_enabled=True,
            ),
        ],
    )
    await storage.create_flag(premium_flag)

    # Flag 5: Gradual rollout (50%)
    gradual_flag = FeatureFlag(
        key="gradual_feature",
        name="Gradual Rollout Feature",
        description="Feature being rolled out to 50% of users",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            FlagRule(
                name="50_percent",
                description="50% rollout",
                priority=1,
                enabled=True,
                conditions=[],
                serve_enabled=True,
                rollout_percentage=50,
            ),
        ],
    )
    await storage.create_flag(gradual_flag)

    print("Decorator example flags created successfully!")


# Route Handlers


@get("/")
async def index() -> dict:
    """List available endpoints and their flag status."""
    return {
        "message": "Decorator Usage Example",
        "endpoints": {
            "/new-feature": "Uses @feature_flag (enabled for all)",
            "/coming-soon": "Uses @feature_flag (disabled for all)",
            "/beta": "Uses @require_flag (beta users only)",
            "/premium": "Uses @require_flag (premium users only)",
            "/gradual": "Uses @feature_flag (50% rollout)",
            "/manual": "Manual flag checking without decorators",
        },
        "tips": [
            "Add ?user_id=xxx to set targeting key",
            "For /beta, add ?is_beta_user=true",
            "For /premium, add ?plan=premium",
        ],
    }


# Example 1: Basic @feature_flag usage
# Returns default_response when flag is disabled
@get("/new-feature")
@feature_flag("new_feature", default_response={"error": "Feature not available"})
async def new_feature_endpoint() -> dict:
    """Endpoint protected by an enabled feature flag.

    The @feature_flag decorator will:
    1. Evaluate the "new_feature" flag
    2. If enabled -> execute the handler
    3. If disabled -> return the default_response

    Since "new_feature" is enabled by default, this endpoint
    will always execute the handler.
    """
    return {
        "message": "Welcome to the new feature!",
        "data": {
            "items": ["item1", "item2", "item3"],
        },
    }


# Example 2: Disabled feature with custom response
@get("/coming-soon")
@feature_flag(
    "coming_soon",
    default=False,
    default_response={
        "status": "coming_soon",
        "message": "This feature is not yet available",
        "expected_release": "Q2 2025",
    },
)
async def coming_soon_endpoint() -> dict:
    """Endpoint for a feature that is not yet released.

    Since "coming_soon" is disabled, users will always
    receive the default_response indicating the feature
    is not yet available.
    """
    return {
        "message": "This is the coming soon feature!",
        "secret_data": "You shouldn't see this yet",
    }


# Example 3: @require_flag with custom error message
@get("/beta")
@require_flag(
    "beta_access",
    error_message="Beta access required. Apply at /beta-signup",
)
async def beta_endpoint(
    request: Request,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Endpoint that requires beta access.

    The @require_flag decorator will:
    1. Evaluate the "beta_access" flag
    2. If enabled -> execute the handler
    3. If disabled -> raise NotAuthorizedException

    To access this endpoint, users need the is_beta_user attribute
    set to True in their context.
    """
    return {
        "message": "Welcome to the beta program!",
        "beta_features": [
            "Advanced AI suggestions",
            "Real-time collaboration",
            "Custom workflows",
        ],
        "feedback_url": "/beta-feedback",
    }


# Example 4: Premium feature with targeting
@get("/premium")
@require_flag(
    "premium_feature",
    error_message="Premium subscription required. Upgrade at /pricing",
)
async def premium_endpoint(
    request: Request,
    feature_flags: FeatureFlagClient,
) -> dict:
    """Endpoint for premium users only.

    Users must have plan="premium" or plan="enterprise"
    in their context to access this endpoint.
    """
    return {
        "message": "Welcome premium user!",
        "premium_content": {
            "reports": ["Revenue Analysis", "User Behavior", "Predictions"],
            "api_limit": "unlimited",
            "support": "priority",
        },
    }


# Example 5: Gradual rollout with @feature_flag
@get("/gradual")
@feature_flag(
    "gradual_feature",
    default_response={
        "status": "not_available",
        "message": "You're not in the rollout group yet",
        "info": "This feature is being gradually rolled out",
    },
)
async def gradual_rollout_endpoint() -> dict:
    """Endpoint with 50% rollout.

    Only 50% of users (based on their targeting key) will
    have access to this endpoint. The same user will
    consistently get the same result.
    """
    return {
        "message": "You're in the rollout group!",
        "feature": "Gradual rollout feature",
        "status": "enabled",
    }


# Example 6: Manual flag checking (for comparison)
@get("/manual")
async def manual_flag_check(
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> dict:
    """Endpoint demonstrating manual flag checking.

    This shows how to check flags manually when you need
    more control than decorators provide.
    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Check multiple flags
    new_feature = await feature_flags.is_enabled("new_feature", context=context)
    beta_access = await feature_flags.is_enabled("beta_access", context=context)
    premium = await feature_flags.is_enabled("premium_feature", context=context)
    gradual = await feature_flags.is_enabled("gradual_feature", context=context)

    return {
        "user_id": user_id,
        "feature_access": {
            "new_feature": new_feature,
            "beta_access": beta_access,
            "premium_feature": premium,
            "gradual_feature": gradual,
        },
        "note": "This demonstrates manual flag checking without decorators",
    }


# Example 7: Combining flags with business logic
@get("/conditional-content")
async def conditional_content(
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> dict:
    """Endpoint that varies content based on feature flags.

    Sometimes you need to show different content rather than
    blocking access entirely. This pattern is useful for
    progressive enhancement.
    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Build response based on enabled features
    response = {
        "base_content": "Welcome to our application!",
        "features": [],
    }

    if await feature_flags.is_enabled("new_feature", context=context):
        response["features"].append(
            {
                "name": "New Feature",
                "description": "Access the new feature dashboard",
                "url": "/new-feature",
            }
        )

    if await feature_flags.is_enabled("beta_access", context=context):
        response["features"].append(
            {
                "name": "Beta Features",
                "description": "Try our latest beta features",
                "url": "/beta",
            }
        )

    if await feature_flags.is_enabled("premium_feature", context=context):
        response["features"].append(
            {
                "name": "Premium Content",
                "description": "Access premium-only content",
                "url": "/premium",
            }
        )

    if not response["features"]:
        response["features"].append(
            {
                "name": "Basic Features",
                "description": "Explore our standard features",
                "url": "/basic",
            }
        )

    return response


# Example 8: Using context_key parameter
# The context_key parameter extracts targeting info from the request
@get("/user/{user_id:str}/profile")
@feature_flag(
    "new_feature",
    default_response={"error": "Profile not available"},
    context_key="user_id",  # Use path parameter as targeting key
)
async def user_profile(user_id: str) -> dict:
    """Endpoint using path parameter for targeting.

    The context_key parameter tells the decorator to use
    the user_id path parameter as the targeting key for
    flag evaluation.
    """
    return {
        "user_id": user_id,
        "profile": {
            "display_name": f"User {user_id}",
            "avatar_url": f"/avatars/{user_id}.png",
        },
    }


# Error handler for NotAuthorizedException
async def handle_not_authorized(request: Request, exc: NotAuthorizedException) -> Response:
    """Custom error handler for feature flag access denial.

    When @require_flag raises NotAuthorizedException, this
    handler provides a user-friendly response.
    """
    return Response(
        content={
            "error": "Access Denied",
            "detail": exc.detail,
            "action": "Please check your subscription or contact support",
        },
        status_code=403,
    )


# Create the Litestar application
app = Litestar(
    route_handlers=[
        index,
        new_feature_endpoint,
        coming_soon_endpoint,
        beta_endpoint,
        premium_endpoint,
        gradual_rollout_endpoint,
        manual_flag_check,
        conditional_content,
        user_profile,
    ],
    plugins=[FeatureFlagsPlugin(config=config)],
    on_startup=[setup_decorator_flags],
    exception_handlers={NotAuthorizedException: handle_not_authorized},
    debug=True,
)


# Standalone decorator demo
async def standalone_decorator_demo() -> None:
    """Demonstrate decorator functionality concepts.

    Note: Decorators are designed to work within Litestar's
    request/response cycle. This demo shows the underlying
    flag evaluation logic.
    """
    print("\n--- Decorator Concepts Demo ---\n")

    storage = MemoryStorageBackend()
    client = FeatureFlagClient(storage=storage)

    # Create sample flags
    enabled_flag = FeatureFlag(
        key="enabled_feature",
        name="Enabled Feature",
        flag_type=FlagType.BOOLEAN,
        default_enabled=True,
    )
    disabled_flag = FeatureFlag(
        key="disabled_feature",
        name="Disabled Feature",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
    )

    await storage.create_flag(enabled_flag)
    await storage.create_flag(disabled_flag)

    context = EvaluationContext(targeting_key="demo-user")

    print("Simulating @feature_flag behavior:")
    print("-" * 50)

    # Simulate @feature_flag for enabled feature
    is_enabled = await client.is_enabled("enabled_feature", context=context)
    if is_enabled:
        print("enabled_feature: Handler would execute")
    else:
        print("enabled_feature: Would return default_response")

    # Simulate @feature_flag for disabled feature
    is_disabled_enabled = await client.is_enabled("disabled_feature", context=context)
    if is_disabled_enabled:
        print("disabled_feature: Handler would execute")
    else:
        print("disabled_feature: Would return default_response")

    print("\n" + "-" * 50)
    print("Simulating @require_flag behavior:")

    # Simulate @require_flag for enabled feature
    if await client.is_enabled("enabled_feature", context=context):
        print("enabled_feature: Handler would execute")
    else:
        print("enabled_feature: Would raise NotAuthorizedException")

    # Simulate @require_flag for disabled feature
    if await client.is_enabled("disabled_feature", context=context):
        print("disabled_feature: Handler would execute")
    else:
        print("disabled_feature: Would raise NotAuthorizedException")

    await client.close()


if __name__ == "__main__":
    asyncio.run(standalone_decorator_demo())
