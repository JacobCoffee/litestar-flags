"""Basic Feature Flag Usage Example.

This example demonstrates the fundamental usage of litestar-flags:
- Setting up a Litestar application with the FeatureFlagsPlugin
- Creating feature flags with MemoryStorageBackend
- Evaluating boolean flags in route handlers
- Using the EvaluationContext for user targeting

To run this example:
    uvicorn examples.basic_usage:app --reload

Then visit:
    - http://localhost:8000/
    - http://localhost:8000/feature?user_id=user-123
    - http://localhost:8000/all-flags
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from litestar import Litestar, get
from litestar.response import Response

from litestar_flags import (
    EvaluationContext,
    FeatureFlag,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    FlagType,
    MemoryStorageBackend,
)

if TYPE_CHECKING:
    from litestar.datastructures import State


# Create the plugin configuration with memory backend (suitable for development)
config = FeatureFlagsConfig(backend="memory")


async def setup_sample_flags(state: State) -> None:
    """Set up sample feature flags on application startup.

    This function creates several example flags to demonstrate
    different flag types and configurations.
    """
    storage: MemoryStorageBackend = state.feature_flags_storage

    # Create a simple boolean feature flag (enabled by default)
    dark_mode_flag = FeatureFlag(
        key="dark_mode",
        name="Dark Mode",
        description="Enable dark mode theme for the application",
        flag_type=FlagType.BOOLEAN,
        default_enabled=True,
    )
    await storage.create_flag(dark_mode_flag)

    # Create a disabled feature flag
    beta_feature_flag = FeatureFlag(
        key="beta_feature",
        name="Beta Feature",
        description="A new feature currently in beta testing",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
    )
    await storage.create_flag(beta_feature_flag)

    # Create a string-type flag for configuration
    welcome_message_flag = FeatureFlag(
        key="welcome_message",
        name="Welcome Message",
        description="Customizable welcome message for users",
        flag_type=FlagType.STRING,
        default_value={"value": "Welcome to our application!"},
    )
    await storage.create_flag(welcome_message_flag)

    print("Sample feature flags created successfully!")


# Route Handlers


@get("/")
async def index() -> dict:
    """Root endpoint with basic information."""
    return {
        "message": "Litestar Feature Flags Example",
        "endpoints": {
            "/feature": "Check a feature flag status",
            "/all-flags": "Get all active feature flags",
        },
    }


@get("/feature")
async def check_feature(
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> dict:
    """Check the status of feature flags.

    This endpoint demonstrates:
    1. Basic boolean flag evaluation
    2. Using EvaluationContext with a targeting key
    3. Getting string flag values

    Args:
        feature_flags: Injected feature flag client
        user_id: Optional user ID for targeting

    Returns:
        Dictionary with flag evaluation results

    """
    # Create an evaluation context with the user's targeting key
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Evaluate boolean flags
    dark_mode_enabled = await feature_flags.get_boolean_value(
        "dark_mode",
        default=False,
        context=context,
    )

    beta_feature_enabled = await feature_flags.get_boolean_value(
        "beta_feature",
        default=False,
        context=context,
    )

    # Evaluate a string flag
    welcome_message_obj = await feature_flags.get_object_value(
        "welcome_message",
        default={"value": "Hello!"},
        context=context,
    )
    welcome_message = welcome_message_obj.get("value", "Hello!")

    # Using the convenience method is_enabled()
    is_dark_mode = await feature_flags.is_enabled("dark_mode", context=context)

    return {
        "user_id": user_id,
        "flags": {
            "dark_mode": dark_mode_enabled,
            "beta_feature": beta_feature_enabled,
            "is_dark_mode": is_dark_mode,
        },
        "welcome_message": welcome_message,
    }


@get("/all-flags")
async def get_all_flags(
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> dict:
    """Get all active feature flags with their evaluation details.

    This endpoint demonstrates bulk flag evaluation, which is useful
    for initial page loads or client-side flag synchronization.

    Args:
        feature_flags: Injected feature flag client
        user_id: Optional user ID for targeting

    Returns:
        Dictionary with all flags and their evaluation details

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Get all flags with evaluation details
    all_flags = await feature_flags.get_all_flags(context=context)

    # Transform the results for JSON response
    flags_response = {}
    for key, details in all_flags.items():
        flags_response[key] = {
            "value": details.value,
            "reason": details.reason.value,
            "variant": details.variant,
        }

    return {
        "user_id": user_id,
        "flags": flags_response,
        "total_flags": len(flags_response),
    }


@get("/flag/{flag_key:str}")
async def get_flag_details(
    flag_key: str,
    feature_flags: FeatureFlagClient,
    user_id: str | None = None,
) -> Response:
    """Get detailed information about a specific flag.

    This endpoint demonstrates getting evaluation details which includes
    the reason for the evaluation result and any error information.

    Args:
        flag_key: The unique key of the flag to evaluate
        feature_flags: Injected feature flag client
        user_id: Optional user ID for targeting

    Returns:
        Detailed evaluation result or error response

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Get detailed evaluation result
    details = await feature_flags.get_boolean_details(
        flag_key,
        default=False,
        context=context,
    )

    response_data = {
        "flag_key": details.flag_key,
        "value": details.value,
        "reason": details.reason.value,
        "variant": details.variant,
        "metadata": details.flag_metadata,
    }

    # Include error information if present
    if details.error_code:
        response_data["error"] = {
            "code": details.error_code.value,
            "message": details.error_message,
        }

    return Response(content=response_data)


@get("/health")
async def health_check(feature_flags: FeatureFlagClient) -> dict:
    """Health check endpoint including feature flags status.

    This demonstrates using the health_check() method to verify
    the feature flags system is operational.

    Args:
        feature_flags: Injected feature flag client

    Returns:
        Health status information

    """
    flags_healthy = await feature_flags.health_check()

    return {
        "status": "healthy" if flags_healthy else "degraded",
        "components": {
            "feature_flags": "healthy" if flags_healthy else "unhealthy",
        },
    }


# Create the Litestar application with the plugin
app = Litestar(
    route_handlers=[
        index,
        check_feature,
        get_all_flags,
        get_flag_details,
        health_check,
    ],
    plugins=[FeatureFlagsPlugin(config=config)],
    on_startup=[setup_sample_flags],
    debug=True,
)


# Standalone demonstration (runs without Litestar server)
async def standalone_demo() -> None:
    """Demonstrate using the FeatureFlagClient directly without Litestar.

    This is useful for:
    - Background jobs
    - CLI applications
    - Testing
    - Scripts
    """
    print("\n--- Standalone Feature Flags Demo ---\n")

    # Create a storage backend
    storage = MemoryStorageBackend()

    # Create the client
    async with FeatureFlagClient(storage=storage) as client:
        # Create a sample flag
        sample_flag = FeatureFlag(
            key="standalone_feature",
            name="Standalone Feature",
            flag_type=FlagType.BOOLEAN,
            default_enabled=True,
        )
        await storage.create_flag(sample_flag)

        # Evaluate the flag
        context = EvaluationContext(targeting_key="user-123")
        is_enabled = await client.is_enabled("standalone_feature", context=context)

        print(f"Feature 'standalone_feature' is enabled: {is_enabled}")

        # Get detailed evaluation
        details = await client.get_boolean_details(
            "standalone_feature",
            default=False,
            context=context,
        )
        print(f"Evaluation reason: {details.reason.value}")

        # Test a non-existent flag (returns default)
        missing_flag = await client.get_boolean_value(
            "non_existent_flag",
            default=False,
            context=context,
        )
        print(f"Non-existent flag returns default: {missing_flag}")


if __name__ == "__main__":
    # Run the standalone demo
    asyncio.run(standalone_demo())
