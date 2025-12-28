"""Percentage Rollout Example.

This example demonstrates gradual feature rollouts using litestar-flags:
- Creating flags with percentage-based rules
- Gradual rollout to increasing percentages of users
- Using targeting rules combined with percentage rollout
- Rollout by user segments (country, plan type, etc.)

Percentage rollouts are useful for:
- Reducing risk when launching new features
- Gradual migration from old to new systems
- Canary deployments and monitoring

To run this example:
    uvicorn examples.percentage_rollout:app --reload

Then visit:
    - http://localhost:8000/
    - http://localhost:8000/feature?user_id=user-123
    - http://localhost:8000/rollout-status
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
    FlagRule,
    FlagType,
    MemoryStorageBackend,
)

if TYPE_CHECKING:
    from litestar.datastructures import State


config = FeatureFlagsConfig(backend="memory")


async def setup_rollout_flags(state: State) -> None:
    """Set up percentage rollout feature flags.

    Creates flags demonstrating various rollout strategies:
    - Simple percentage rollout
    - Segment-based rollout
    - Gradual rollout with multiple rules
    """
    storage: MemoryStorageBackend = state.feature_flags_storage

    # Example 1: Simple percentage rollout
    # 25% of users get the new feature
    simple_rollout = FeatureFlag(
        key="new_search_algorithm",
        name="New Search Algorithm",
        description="Improved search with ML-based ranking",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,  # Default is off
        rules=[
            FlagRule(
                name="25_percent_rollout",
                description="Roll out to 25% of users",
                priority=1,
                enabled=True,
                conditions=[],  # No conditions = applies to all users
                serve_enabled=True,
                rollout_percentage=25,  # Only 25% of users
            ),
        ],
    )
    await storage.create_flag(simple_rollout)

    # Example 2: Segment-based rollout
    # 100% rollout to premium users, 10% to free users
    segment_rollout = FeatureFlag(
        key="advanced_analytics",
        name="Advanced Analytics Dashboard",
        description="New analytics features with predictive insights",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            # Rule 1: All premium users get the feature (100%)
            FlagRule(
                name="premium_users",
                description="Full rollout to premium users",
                priority=1,  # Higher priority (evaluated first)
                enabled=True,
                conditions=[
                    {"attribute": "plan", "operator": "eq", "value": "premium"},
                ],
                serve_enabled=True,
                rollout_percentage=100,  # All matching users
            ),
            # Rule 2: 10% of free users get the feature
            FlagRule(
                name="free_users_beta",
                description="Limited rollout to free users",
                priority=2,  # Lower priority
                enabled=True,
                conditions=[
                    {"attribute": "plan", "operator": "eq", "value": "free"},
                ],
                serve_enabled=True,
                rollout_percentage=10,  # Only 10% of free users
            ),
        ],
    )
    await storage.create_flag(segment_rollout)

    # Example 3: Geographic rollout
    # Roll out gradually by region
    geo_rollout = FeatureFlag(
        key="new_payment_processor",
        name="New Payment Processor",
        description="Migration to new payment infrastructure",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            # Already fully rolled out in Canada
            FlagRule(
                name="canada_full",
                description="Full rollout in Canada",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "country", "operator": "eq", "value": "CA"},
                ],
                serve_enabled=True,
                rollout_percentage=100,
            ),
            # 50% rollout in US
            FlagRule(
                name="us_partial",
                description="50% rollout in United States",
                priority=2,
                enabled=True,
                conditions=[
                    {"attribute": "country", "operator": "eq", "value": "US"},
                ],
                serve_enabled=True,
                rollout_percentage=50,
            ),
            # 10% rollout in EU countries
            FlagRule(
                name="eu_beta",
                description="10% beta rollout in EU",
                priority=3,
                enabled=True,
                conditions=[
                    {"attribute": "country", "operator": "in", "value": ["DE", "FR", "GB", "ES", "IT"]},
                ],
                serve_enabled=True,
                rollout_percentage=10,
            ),
        ],
    )
    await storage.create_flag(geo_rollout)

    # Example 4: Version-based rollout
    # Roll out based on app version (semver)
    version_rollout = FeatureFlag(
        key="new_ui_components",
        name="New UI Component Library",
        description="React component library v2",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            # Users with app version >= 2.0.0 get the feature
            FlagRule(
                name="version_2_plus",
                description="Available for app version 2.0.0 and above",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "app_version", "operator": "semver_gt", "value": "1.9.9"},
                ],
                serve_enabled=True,
                rollout_percentage=100,
            ),
            # 25% of v1.x users get the feature for testing
            FlagRule(
                name="version_1_beta",
                description="Beta testing for v1.x users",
                priority=2,
                enabled=True,
                conditions=[
                    {"attribute": "app_version", "operator": "semver_gt", "value": "0.9.9"},
                    {"attribute": "app_version", "operator": "semver_lt", "value": "2.0.0"},
                ],
                serve_enabled=True,
                rollout_percentage=25,
            ),
        ],
    )
    await storage.create_flag(version_rollout)

    # Example 5: Employee/internal rollout first
    internal_first = FeatureFlag(
        key="experimental_feature",
        name="Experimental Feature",
        description="Testing internally before public release",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            # All internal users (employees)
            FlagRule(
                name="internal_users",
                description="All internal/employee users",
                priority=1,
                enabled=True,
                conditions=[
                    {"attribute": "is_employee", "operator": "eq", "value": True},
                ],
                serve_enabled=True,
                rollout_percentage=100,
            ),
            # Beta testers
            FlagRule(
                name="beta_testers",
                description="Registered beta testers",
                priority=2,
                enabled=True,
                conditions=[
                    {"attribute": "is_beta_tester", "operator": "eq", "value": True},
                ],
                serve_enabled=True,
                rollout_percentage=100,
            ),
            # 1% of regular users
            FlagRule(
                name="public_canary",
                description="1% canary for public users",
                priority=3,
                enabled=True,
                conditions=[],
                serve_enabled=True,
                rollout_percentage=1,
            ),
        ],
    )
    await storage.create_flag(internal_first)

    print("Percentage rollout flags created successfully!")


# Route Handlers


@get("/")
async def index() -> dict:
    """List available endpoints and explain rollout concepts."""
    return {
        "message": "Percentage Rollout Example",
        "description": "Demonstrates gradual feature rollouts",
        "endpoints": {
            "/feature": "Check a feature with user_id",
            "/rollout-status": "See rollout status for all features",
            "/simulate": "Simulate rollout distribution",
            "/check-access": "Check feature access with full context",
        },
        "rollout_strategies": [
            "Simple percentage: X% of all users",
            "Segment-based: Different percentages per user segment",
            "Geographic: Rollout by country/region",
            "Version-based: Rollout by app version",
            "Internal first: Employees -> Beta -> Public",
        ],
    }


@get("/feature")
async def check_feature(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
) -> dict:
    """Check the simple percentage rollout feature.

    The same user will consistently be included or excluded
    from the rollout based on their user_id.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier for consistent assignment

    Returns:
        Feature access status

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
    )

    details = await feature_flags.get_boolean_details(
        "new_search_algorithm",
        default=False,
        context=context,
    )

    return {
        "user_id": user_id,
        "feature": "new_search_algorithm",
        "enabled": details.value,
        "reason": details.reason.value,
        "matched_rule": details.variant,
        "note": "Try different user_ids - about 25% will have access",
    }


@get("/check-access")
async def check_access_with_context(
    feature_flags: FeatureFlagClient,
    user_id: str = "anonymous",
    plan: str = "free",
    country: str = "US",
    app_version: str = "1.0.0",
    is_employee: bool = False,
    is_beta_tester: bool = False,
) -> dict:
    """Check feature access with full context attributes.

    Demonstrates how different context attributes affect
    feature access through targeting rules.

    Args:
        feature_flags: Injected feature flag client
        user_id: User identifier
        plan: User's subscription plan (free/premium)
        country: User's country code
        app_version: User's app version
        is_employee: Whether user is an employee
        is_beta_tester: Whether user is a beta tester

    Returns:
        Access status for all rollout features

    """
    context = EvaluationContext(
        targeting_key=user_id,
        user_id=user_id,
        country=country,
        app_version=app_version,
        attributes={
            "plan": plan,
            "is_employee": is_employee,
            "is_beta_tester": is_beta_tester,
        },
    )

    # Check all rollout features
    features = [
        "new_search_algorithm",
        "advanced_analytics",
        "new_payment_processor",
        "new_ui_components",
        "experimental_feature",
    ]

    results = {}
    for feature in features:
        details = await feature_flags.get_boolean_details(
            feature,
            default=False,
            context=context,
        )
        results[feature] = {
            "enabled": details.value,
            "reason": details.reason.value,
            "matched_rule": details.variant,
        }

    return {
        "user_context": {
            "user_id": user_id,
            "plan": plan,
            "country": country,
            "app_version": app_version,
            "is_employee": is_employee,
            "is_beta_tester": is_beta_tester,
        },
        "feature_access": results,
    }


@get("/rollout-status")
async def get_rollout_status(
    feature_flags: FeatureFlagClient,
) -> dict:
    """Get the current rollout status for all features.

    Shows the rollout configuration for each flag.

    Args:
        feature_flags: Injected feature flag client

    Returns:
        Rollout configuration for all flags

    """
    all_flags = await feature_flags.storage.get_all_active_flags()

    rollout_info = {}
    for flag in all_flags:
        rules_info = []
        for rule in sorted(flag.rules, key=lambda r: r.priority):
            rules_info.append(
                {
                    "name": rule.name,
                    "description": rule.description,
                    "priority": rule.priority,
                    "conditions": rule.conditions,
                    "rollout_percentage": rule.rollout_percentage,
                    "enabled": rule.enabled,
                }
            )

        rollout_info[flag.key] = {
            "name": flag.name,
            "description": flag.description,
            "default_enabled": flag.default_enabled,
            "rules": rules_info,
        }

    return {
        "rollout_configurations": rollout_info,
    }


@get("/simulate")
async def simulate_rollout(
    feature_flags: FeatureFlagClient,
    feature: str = "new_search_algorithm",
    sample_size: int = 1000,
) -> dict:
    """Simulate rollout distribution across many users.

    Demonstrates the actual distribution of a percentage rollout.

    Args:
        feature_flags: Injected feature flag client
        feature: Feature flag key to simulate
        sample_size: Number of simulated users

    Returns:
        Distribution statistics

    """
    enabled_count = 0
    disabled_count = 0

    for i in range(sample_size):
        context = EvaluationContext(
            targeting_key=f"simulated-user-{i}",
            user_id=f"simulated-user-{i}",
        )

        is_enabled = await feature_flags.get_boolean_value(
            feature,
            default=False,
            context=context,
        )

        if is_enabled:
            enabled_count += 1
        else:
            disabled_count += 1

    enabled_percentage = round((enabled_count / sample_size) * 100, 2)

    return {
        "feature": feature,
        "sample_size": sample_size,
        "distribution": {
            "enabled": {
                "count": enabled_count,
                "percentage": enabled_percentage,
            },
            "disabled": {
                "count": disabled_count,
                "percentage": round(100 - enabled_percentage, 2),
            },
        },
    }


@get("/simulate-segments")
async def simulate_segment_rollout(
    feature_flags: FeatureFlagClient,
    sample_size: int = 500,
) -> dict:
    """Simulate segment-based rollout distribution.

    Shows how different user segments receive different
    rollout percentages for the advanced_analytics feature.

    Args:
        feature_flags: Injected feature flag client
        sample_size: Number of users per segment

    Returns:
        Distribution statistics per segment

    """
    segments = {
        "premium": {"plan": "premium"},
        "free": {"plan": "free"},
        "no_plan": {},  # Users without a plan attribute
    }

    results = {}

    for segment_name, attributes in segments.items():
        enabled_count = 0

        for i in range(sample_size):
            context = EvaluationContext(
                targeting_key=f"{segment_name}-user-{i}",
                user_id=f"{segment_name}-user-{i}",
                attributes=attributes,
            )

            is_enabled = await feature_flags.get_boolean_value(
                "advanced_analytics",
                default=False,
                context=context,
            )

            if is_enabled:
                enabled_count += 1

        results[segment_name] = {
            "sample_size": sample_size,
            "enabled_count": enabled_count,
            "percentage": round((enabled_count / sample_size) * 100, 2),
            "attributes": attributes,
        }

    return {
        "feature": "advanced_analytics",
        "segment_distribution": results,
        "expected": {
            "premium": "~100% (full rollout)",
            "free": "~10% (limited rollout)",
            "no_plan": "~0% (no matching rule)",
        },
    }


# Create the Litestar application
app = Litestar(
    route_handlers=[
        index,
        check_feature,
        check_access_with_context,
        get_rollout_status,
        simulate_rollout,
        simulate_segment_rollout,
    ],
    plugins=[FeatureFlagsPlugin(config=config)],
    on_startup=[setup_rollout_flags],
    debug=True,
)


# Standalone rollout demo
async def standalone_rollout_demo() -> None:
    """Demonstrate percentage rollout functionality directly."""
    print("\n--- Standalone Percentage Rollout Demo ---\n")

    storage = MemoryStorageBackend()
    client = FeatureFlagClient(storage=storage)

    # Create a 30% rollout flag
    rollout_flag = FeatureFlag(
        key="demo_feature",
        name="Demo Feature",
        description="30% rollout demonstration",
        flag_type=FlagType.BOOLEAN,
        default_enabled=False,
        rules=[
            FlagRule(
                name="30_percent",
                description="30% of users",
                priority=1,
                enabled=True,
                conditions=[],
                serve_enabled=True,
                rollout_percentage=30,
            ),
        ],
    )
    await storage.create_flag(rollout_flag)

    print("Testing 30% rollout across 1000 users:")
    print("-" * 50)

    enabled_count = 0
    sample_users = []

    for i in range(1000):
        user_id = f"user-{i:04d}"
        context = EvaluationContext(targeting_key=user_id)
        is_enabled = await client.is_enabled("demo_feature", context=context)

        if is_enabled:
            enabled_count += 1
            if len(sample_users) < 5:
                sample_users.append(user_id)

    percentage = (enabled_count / 1000) * 100
    print(f"Enabled: {enabled_count}/1000 ({percentage:.1f}%)")
    print("Expected: ~300/1000 (30%)")
    print(f"\nSample enabled users: {', '.join(sample_users)}")

    print("\n" + "-" * 50)
    print("Verifying consistency (same user, 5 evaluations):")

    for user_id in sample_users[:2]:
        results = []
        for _ in range(5):
            context = EvaluationContext(targeting_key=user_id)
            is_enabled = await client.is_enabled("demo_feature", context=context)
            results.append(is_enabled)
        print(f"{user_id}: {results} (all same: {len(set(results)) == 1})")

    await client.close()


if __name__ == "__main__":
    asyncio.run(standalone_rollout_demo())
