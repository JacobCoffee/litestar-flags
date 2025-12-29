"""Litestar Feature Flags - Production-ready feature flags for Litestar.

A comprehensive feature flag library designed specifically for the Litestar
ecosystem, following OpenFeature specification patterns and integrating
seamlessly with Advanced-Alchemy for database persistence.

Example:
    Basic usage with memory backend::

        from litestar import Litestar, get
        from litestar_flags import (
            FeatureFlagsPlugin,
            FeatureFlagsConfig,
            FeatureFlagClient,
            EvaluationContext,
        )

        config = FeatureFlagsConfig(backend="memory")
        app = Litestar(
            route_handlers=[...],
            plugins=[FeatureFlagsPlugin(config=config)],
        )

        @get("/feature")
        async def check_feature(
            feature_flags: FeatureFlagClient,
            user_id: str,
        ) -> dict:
            context = EvaluationContext(targeting_key=user_id)
            enabled = await feature_flags.get_boolean_value(
                "my_feature",
                context=context,
            )
            return {"enabled": enabled}

    Using decorators::

        from litestar_flags import feature_flag, require_flag

        @get("/new-feature")
        @feature_flag("new_feature", default_response={"error": "Not available"})
        async def new_feature() -> dict:
            return {"message": "New feature!"}

        @get("/beta")
        @require_flag("beta_access")
        async def beta_only() -> dict:
            return {"message": "Beta content"}

"""

from __future__ import annotations

from litestar_flags.bootstrap import BootstrapConfig, BootstrapLoader, OfflineClient
from litestar_flags.cache import CacheProtocol, CacheStats, LRUCache, RedisCache
from litestar_flags.client import FeatureFlagClient
from litestar_flags.config import FeatureFlagsConfig
from litestar_flags.context import EvaluationContext
from litestar_flags.decorators import feature_flag, require_flag
from litestar_flags.engine import EvaluationEngine
from litestar_flags.exceptions import (
    ConfigurationError,
    FeatureFlagError,
    FlagNotFoundError,
    RateLimitExceededError,
    StorageError,
)
from litestar_flags.health import HealthCheckResult, HealthStatus, health_check
from litestar_flags.middleware import (
    FeatureFlagsMiddleware,
    create_context_middleware,
    get_request_context,
)
from litestar_flags.plugin import FeatureFlagsPlugin
from litestar_flags.protocols import StorageBackend
from litestar_flags.rate_limit import (
    RateLimitConfig,
    RateLimiter,
    RateLimitHook,
    TokenBucketRateLimiter,
)
from litestar_flags.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    ResilienceConfig,
    RetryPolicy,
    resilient_call,
)
from litestar_flags.results import EvaluationDetails
from litestar_flags.schedule_processor import ScheduleProcessor, ScheduleProcessorTask
from litestar_flags.security import (
    SENSITIVE_FIELDS,
    create_safe_log_context,
    hash_targeting_key,
    is_sensitive_field,
    sanitize_log_context,
    validate_flag_key,
)
from litestar_flags.segment_evaluator import CircularSegmentReferenceError, SegmentEvaluator
from litestar_flags.storage import MemoryStorageBackend, ResilientStorageBackend, with_resilience
from litestar_flags.time_rules import TimeBasedRuleEvaluator
from litestar_flags.types import (
    ChangeType,
    ErrorCode,
    EvaluationReason,
    FlagStatus,
    FlagType,
    RecurrenceType,
    RuleOperator,
)

__all__ = [
    "SENSITIVE_FIELDS",
    "BootstrapConfig",
    "BootstrapLoader",
    "CacheProtocol",
    "CacheStats",
    "ChangeType",
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "CircularSegmentReferenceError",
    "ConfigurationError",
    "ErrorCode",
    "EvaluationContext",
    "EvaluationDetails",
    "EvaluationEngine",
    "EvaluationReason",
    "FeatureFlagClient",
    "FeatureFlagError",
    "FeatureFlagsConfig",
    "FeatureFlagsMiddleware",
    "FeatureFlagsPlugin",
    "FlagNotFoundError",
    "FlagStatus",
    "FlagType",
    "HealthCheckResult",
    "HealthStatus",
    "LRUCache",
    "MemoryStorageBackend",
    "OfflineClient",
    "RateLimitConfig",
    "RateLimitExceededError",
    "RateLimitHook",
    "RateLimiter",
    "RecurrenceType",
    "RedisCache",
    "ResilienceConfig",
    "ResilientStorageBackend",
    "RetryPolicy",
    "RuleOperator",
    "ScheduleProcessor",
    "ScheduleProcessorTask",
    "SegmentEvaluator",
    "StorageBackend",
    "StorageError",
    "TimeBasedRuleEvaluator",
    "TokenBucketRateLimiter",
    "create_context_middleware",
    "create_safe_log_context",
    "feature_flag",
    "get_request_context",
    "hash_targeting_key",
    "health_check",
    "is_sensitive_field",
    "require_flag",
    "resilient_call",
    "sanitize_log_context",
    "validate_flag_key",
    "with_resilience",
]

__version__ = "0.1.0"

# Conditionally export database storage
try:
    from litestar_flags.storage.database import DatabaseStorageBackend  # noqa: F401

    __all__.append("DatabaseStorageBackend")
except ImportError:
    pass

# Conditionally export redis storage
try:
    from litestar_flags.storage.redis import RedisStorageBackend  # noqa: F401

    __all__.append("RedisStorageBackend")
except ImportError:
    pass

# Conditionally export models
try:
    from litestar_flags.models import (  # noqa: F401
        FeatureFlag,
        FlagOverride,
        FlagRule,
        FlagVariant,
        Segment,
    )
    from litestar_flags.models.schedule import (  # noqa: F401
        RolloutPhase,
        ScheduledFlagChange,
        TimeSchedule,
    )

    __all__.extend(
        [
            "FeatureFlag",
            "FlagOverride",
            "FlagRule",
            "FlagVariant",
            "RolloutPhase",
            "ScheduledFlagChange",
            "Segment",
            "TimeSchedule",
        ]
    )
except ImportError:
    pass

# Conditionally export contrib modules
# LoggingHook is always available (stdlib logging fallback)
try:
    from litestar_flags.contrib.logging import LoggingHook  # noqa: F401

    __all__.append("LoggingHook")
except ImportError:
    pass

# OTelHook requires opentelemetry-api
try:
    from litestar_flags.contrib.otel import OTelHook  # noqa: F401

    __all__.append("OTelHook")
except ImportError:
    pass

# Cache invalidation hook (always available)
try:
    from litestar_flags.contrib.cache_invalidation import (  # noqa: F401
        CacheInvalidationHook,
        CacheInvalidationMiddleware,
    )

    __all__.extend(["CacheInvalidationHook", "CacheInvalidationMiddleware"])
except ImportError:
    pass

# Conditionally export workflows integration
try:
    from litestar_flags.contrib.workflows import (  # noqa: F401
        ApplyFlagChangeStep,
        FlagApprovalWorkflow,
        FlagChangeRequest,
        ManagerApprovalStep,
        NotifyStakeholdersStep,
        QAValidationStep,
        RolloutStage,
        RolloutStep,
        ScheduledRolloutWorkflow,
        ValidateFlagChangeStep,
    )

    __all__.extend(
        [
            "ApplyFlagChangeStep",
            "FlagApprovalWorkflow",
            "FlagChangeRequest",
            "ManagerApprovalStep",
            "NotifyStakeholdersStep",
            "QAValidationStep",
            "RolloutStage",
            "RolloutStep",
            "ScheduledRolloutWorkflow",
            "ValidateFlagChangeStep",
        ]
    )
except ImportError:
    pass
