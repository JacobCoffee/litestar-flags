"""A/B Testing Example.

This example demonstrates using litestar-flags for A/B testing:
- Creating multivariate flags with variants
- Configuring variant weights for traffic distribution
- Consistent variant assignment using user targeting keys
- Evaluating which variant a user receives

A/B testing allows you to experiment with different feature variations
and measure their impact on user behavior.

To run this example:
    uvicorn examples.ab_testing:app --reload

Then visit:
    - http://localhost:8000/experiment?user_id=user-123
    - http://localhost:8000/experiment?user_id=user-456
    - http://localhost:8000/button-color?user_id=user-789
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from litestar import Litestar, get

from litestar_flags import (
    EvaluationContext,
    FeatureFlag,
    FeatureFlagClient,
    FeatureFlagsConfig,
    FeatureFlagsPlugin,
    FlagType,
    FlagVariant,
    MemoryStorageBackend,
)

if TYPE_CHECKING:
    from litestar.datastructures import State


config = FeatureFlagsConfig(backend="memory")


async def setup_ab_test_flags(state: State) -> None:
    """Set up A/B testing feature flags.

    Creates several multivariate flags with different variant configurations
    to demonstrate various A/B testing scenarios.
    """
    storage: MemoryStorageBackend = state.feature_flags_storage

    # Example 1: Simple A/B test (50/50 split)
    # This is a classic A/B test where users are evenly split between
    # a control group and a treatment group.
    simple_ab_test = FeatureFlag(
        key="checkout_flow_experiment",
        name="Checkout Flow Experiment",
        description="Test new streamlined checkout flow vs. existing flow",
        flag_type=FlagType.STRING,
        default_enabled=True,
        variants=[
            FlagVariant(
                key="control",
                name="Control (Original)",
                description="Original checkout flow",
                value={"checkout_version": "v1", "show_progress_bar": False},
                weight=50,
            ),
            FlagVariant(
                key="treatment",
                name="Treatment (New)",
                description="New streamlined checkout flow",
                value={"checkout_version": "v2", "show_progress_bar": True},
                weight=50,
            ),
        ],
    )
    await storage.create_flag(simple_ab_test)

    # Example 2: Multivariate test with multiple variants
    # Testing multiple button colors to see which performs best
    button_color_test = FeatureFlag(
        key="button_color_test",
        name="CTA Button Color Test",
        description="Test different CTA button colors for conversion optimization",
        flag_type=FlagType.JSON,
        default_enabled=True,
        variants=[
            FlagVariant(
                key="blue",
                name="Blue Button",
                value={"color": "#007bff", "text_color": "#ffffff"},
                weight=25,
            ),
            FlagVariant(
                key="green",
                name="Green Button",
                value={"color": "#28a745", "text_color": "#ffffff"},
                weight=25,
            ),
            FlagVariant(
                key="orange",
                name="Orange Button",
                value={"color": "#fd7e14", "text_color": "#000000"},
                weight=25,
            ),
            FlagVariant(
                key="purple",
                name="Purple Button",
                value={"color": "#6f42c1", "text_color": "#ffffff"},
                weight=25,
            ),
        ],
    )
    await storage.create_flag(button_color_test)

    # Example 3: Weighted rollout (gradual feature launch)
    # Only 10% of users get the new feature initially
    weighted_rollout = FeatureFlag(
        key="new_dashboard",
        name="New Dashboard Rollout",
        description="Gradual rollout of the redesigned dashboard",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        variants=[
            FlagVariant(
                key="legacy",
                name="Legacy Dashboard",
                value={"enabled": False, "version": "legacy"},
                weight=90,
            ),
            FlagVariant(
                key="new",
                name="New Dashboard",
                value={"enabled": True, "version": "2.0"},
                weight=10,
            ),
        ],
    )
    await storage.create_flag(weighted_rollout)

    # Example 4: Pricing tier experiment
    pricing_experiment = FeatureFlag(
        key="pricing_experiment",
        name="Pricing Page Experiment",
        description="Test different pricing display formats",
        flag_type=FlagType.JSON,
        default_enabled=True,
        variants=[
            FlagVariant(
                key="monthly",
                name="Monthly First",
                description="Show monthly pricing prominently",
                value={
                    "display_order": "monthly_first",
                    "highlight_plan": "professional",
                    "show_annual_savings": True,
                },
                weight=33,
            ),
            FlagVariant(
                key="annual",
                name="Annual First",
                description="Show annual pricing prominently with savings",
                value={
                    "display_order": "annual_first",
                    "highlight_plan": "professional",
                    "show_annual_savings": True,
                },
                weight=34,
            ),
            FlagVariant(
                key="comparison",
                name="Side by Side",
                description="Show monthly and annual side by side",
                value={
                    "display_order": "side_by_side",
                    "highlight_plan": "team",
                    "show_annual_savings": True,
                },
                weight=33,
            ),
        ],
    )
    await storage.create_flag(pricing_experiment)

    print("A/B testing flags created successfully!")


# Route Handlers


@get("/")
async def index() -> dict:
    """List available A/B testing endpoints."""
    return {
        "message": "A/B Testing Example",
        "description": "Demonstrates multivariate feature flags for experimentation",
        "endpoints": {
            "/experiment": "Get checkout flow variant",
            "/button-color": "Get button color variant",
            "/dashboard": "Check new dashboard access",
            "/pricing": "Get pricing experiment variant",
            "/all-variants": "See all variant assignments for a user",
        },
        "note": "Pass ?user_id=xxx to see consistent variant assignment",
    }


@get("/experiment")
async def get_experiment_variant(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Get the checkout flow experiment variant for a user.

    Demonstrates a simple A/B test where users are consistently
    assigned to either control or treatment group.

    The same user_id will always receive the same variant due to
    the consistent hashing algorithm used for assignment.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        The assigned variant and its configuration

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Get the variant value (returns the variant's value object)
    details = await feature_flags.get_object_details(
        "checkout_flow_experiment",
        default={"checkout_version": "v1", "show_progress_bar": False},
        context=context,
    )

    return {
        "user_id": user_id,
        "experiment": "checkout_flow_experiment",
        "variant": details.variant,
        "config": details.value,
        "reason": details.reason.value,
        "tip": "Try different user_ids to see how users are distributed between variants",
    }


@get("/button-color")
async def get_button_color(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Get the CTA button color for a user.

    Demonstrates a multivariate test with four equally-weighted
    variants (25% each).

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        The assigned button color configuration

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    details = await feature_flags.get_object_details(
        "button_color_test",
        default={"color": "#6c757d", "text_color": "#ffffff"},
        context=context,
    )

    # Extract the color values
    button_config = details.value

    return {
        "user_id": user_id,
        "experiment": "button_color_test",
        "variant": details.variant,
        "button_style": {
            "background_color": button_config.get("color"),
            "text_color": button_config.get("text_color"),
        },
        "css_snippet": f"background-color: {button_config.get('color')}; color: {button_config.get('text_color')};",
    }


@get("/dashboard")
async def check_dashboard_access(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Check if user has access to the new dashboard.

    Demonstrates a weighted rollout where only 10% of users
    get access to the new feature.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        Dashboard access status and version

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    details = await feature_flags.get_object_details(
        "new_dashboard",
        default={"enabled": False, "version": "legacy"},
        context=context,
    )

    dashboard_config = details.value

    return {
        "user_id": user_id,
        "experiment": "new_dashboard",
        "variant": details.variant,
        "has_new_dashboard": dashboard_config.get("enabled", False),
        "dashboard_version": dashboard_config.get("version", "legacy"),
        "note": "Only ~10% of users will see the new dashboard",
    }


@get("/pricing")
async def get_pricing_variant(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Get the pricing page configuration for a user.

    Demonstrates a three-way multivariate test for pricing
    page optimization.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        Pricing page display configuration

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    details = await feature_flags.get_object_details(
        "pricing_experiment",
        default={
            "display_order": "monthly_first",
            "highlight_plan": "professional",
            "show_annual_savings": False,
        },
        context=context,
    )

    return {
        "user_id": user_id,
        "experiment": "pricing_experiment",
        "variant": details.variant,
        "pricing_config": details.value,
    }


@get("/all-variants")
async def get_all_variants(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Get all experiment variant assignments for a user.

    This endpoint shows how a single user is assigned to
    different variants across all active experiments.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        All variant assignments for the user

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    # Evaluate all flags for this user
    all_flags = await feature_flags.get_all_flags(context=context)

    variants = {}
    for key, details in all_flags.items():
        variants[key] = {
            "variant": details.variant,
            "value": details.value,
            "reason": details.reason.value,
        }

    return {
        "user_id": user_id,
        "experiments": variants,
        "total_experiments": len(variants),
    }


@get("/distribution-test")
async def test_distribution(
    feature_flags: FeatureFlagClient,
    sample_size: int = 1000,
) -> dict:
    """Test variant distribution across many users.

    This endpoint demonstrates the distribution of variants
    across a sample of users to verify the weights are correct.

    Args:
        feature_flags: Injected feature flag client
        sample_size: Number of simulated users

    Returns:
        Distribution statistics for each experiment

    """
    experiments = [
        "checkout_flow_experiment",
        "button_color_test",
        "new_dashboard",
    ]

    results = {}

    for experiment in experiments:
        variant_counts: dict[str, int] = {}

        for i in range(sample_size):
            context = EvaluationContext(
                targeting_key=f"test-user-{i}",
                user_id=f"test-user-{i}",
            )

            details = await feature_flags.get_object_details(
                experiment,
                default={},
                context=context,
            )

            variant = details.variant or "default"
            variant_counts[variant] = variant_counts.get(variant, 0) + 1

        # Calculate percentages
        distribution = {
            variant: {
                "count": count,
                "percentage": round((count / sample_size) * 100, 1),
            }
            for variant, count in sorted(variant_counts.items())
        }

        results[experiment] = distribution

    return {
        "sample_size": sample_size,
        "distribution": results,
    }


# Create the Litestar application
app = Litestar(
    route_handlers=[
        index,
        get_experiment_variant,
        get_button_color,
        check_dashboard_access,
        get_pricing_variant,
        get_all_variants,
        test_distribution,
    ],
    plugins=[FeatureFlagsPlugin(config=config)],
    on_startup=[setup_ab_test_flags],
    debug=True,
)


# Standalone A/B testing demo
async def standalone_ab_demo() -> None:
    """Demonstrate A/B testing functionality directly.

    Shows how the consistent hashing ensures the same user
    always gets the same variant.
    """
    print("\n--- Standalone A/B Testing Demo ---\n")

    storage = MemoryStorageBackend()
    client = FeatureFlagClient(storage=storage)

    # Create variants for the A/B test
    # Note: When creating flags programmatically, the variants list needs
    # to be attached to the flag
    variant_signup = FlagVariant(
        key="signup",
        name="Sign Up",
        value={"text": "Sign Up Free"},
        weight=50,
    )
    variant_get_started = FlagVariant(
        key="get_started",
        name="Get Started",
        value={"text": "Get Started"},
        weight=50,
    )

    # Create a simple A/B test flag with variants
    # Use FlagType.JSON for object values
    ab_flag = FeatureFlag(
        key="signup_button_text",
        name="Signup Button Text Test",
        flag_type=FlagType.JSON,
        default_enabled=True,
        variants=[variant_signup, variant_get_started],
    )

    # Link variants to flag (important for dataclass version)
    variant_signup.flag_id = ab_flag.id
    variant_get_started.flag_id = ab_flag.id

    await storage.create_flag(ab_flag)

    print("Testing consistent variant assignment:")
    print("-" * 50)

    # Show that the same user always gets the same variant
    test_users = ["alice", "bob", "charlie", "diana", "eve"]

    for user_id in test_users:
        context = EvaluationContext(targeting_key=user_id)
        details = await client.get_object_details(
            "signup_button_text",
            default={"text": "Sign Up"},
            context=context,
        )
        variant_name = details.variant or "default"
        text_value = details.value.get("text") if isinstance(details.value, dict) else "N/A"
        print(f"User {user_id:10} -> Variant: {variant_name:15} -> Text: {text_value}")

    print("\n" + "-" * 50)
    print("Verifying consistency (same user, multiple evaluations):")

    # Verify the same user gets the same result multiple times
    for _ in range(3):
        context = EvaluationContext(targeting_key="alice")
        details = await client.get_object_details(
            "signup_button_text",
            default={"text": "Sign Up"},
            context=context,
        )
        variant_name = details.variant or "default"
        print(f"Alice -> {variant_name}")

    print("\n" + "-" * 50)
    print("Distribution test (1000 users):")

    # Test the distribution
    variant_counts: dict[str, int] = {}
    for i in range(1000):
        context = EvaluationContext(targeting_key=f"user-{i}")
        details = await client.get_object_details(
            "signup_button_text",
            default={"text": "Sign Up"},
            context=context,
        )
        variant = details.variant or "default"
        variant_counts[variant] = variant_counts.get(variant, 0) + 1

    for variant, count in sorted(variant_counts.items()):
        print(f"  {variant}: {count} ({count/10:.1f}%)")

    await client.close()


if __name__ == "__main__":
    asyncio.run(standalone_ab_demo())
