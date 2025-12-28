"""Storage backends for feature flags."""

from __future__ import annotations

from litestar_flags.storage.memory import MemoryStorageBackend
from litestar_flags.storage.resilient import ResilientStorageBackend, with_resilience

__all__ = ["MemoryStorageBackend", "ResilientStorageBackend", "with_resilience"]

# Conditionally export database backend if advanced-alchemy is available
try:
    from litestar_flags.storage.database import DatabaseStorageBackend  # noqa: F401

    __all__.append("DatabaseStorageBackend")
except ImportError:
    pass

# Conditionally export redis backend if redis is available
try:
    from litestar_flags.storage.redis import RedisStorageBackend  # noqa: F401

    __all__.append("RedisStorageBackend")
except ImportError:
    pass
