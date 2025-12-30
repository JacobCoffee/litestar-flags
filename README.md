# litestar-flags

Production-ready feature flags for [Litestar](https://litestar.dev) applications.

[![PyPI version](https://badge.fury.io/py/litestar-flags.svg)](https://badge.fury.io/py/litestar-flags)
[![Python versions](https://img.shields.io/pypi/pyversions/litestar-flags.svg)](https://pypi.org/project/litestar-flags/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
uv add litestar-flags

# With extras
uv add litestar-flags[redis]        # Redis backend
uv add litestar-flags[database]     # SQLAlchemy backend
uv add litestar-flags[workflows]    # Approval workflows
uv add litestar-flags[openfeature]  # OpenFeature SDK provider
uv add litestar-flags[prometheus]   # Prometheus metrics
uv add litestar-flags[observability] # OpenTelemetry + structlog
uv add litestar-flags[all]          # Everything
```

## Quick Start

```python
from litestar import Litestar, get
from litestar_flags import FeatureFlagsPlugin, FeatureFlagsConfig, FeatureFlagClient

config = FeatureFlagsConfig()
plugin = FeatureFlagsPlugin(config=config)

@get("/")
async def index(feature_flags: FeatureFlagClient) -> dict:
    if await feature_flags.is_enabled("new_checkout"):
        return {"flow": "new"}
    return {"flow": "legacy"}

app = Litestar(plugins=[plugin])
```

## Features

- **Multiple backends** - Memory, Redis, and SQLAlchemy storage
- **Percentage rollouts** - Gradual releases with consistent hashing
- **User targeting** - Rules based on user attributes
- **Segment-based targeting** - Reusable user groups for complex targeting
- **A/B testing** - Weighted variants for experiments
- **Time-based rules** - Scheduled launches and maintenance windows
- **Multi-environment** - Environment inheritance, promotion, and per-env configs
- **Admin API** - REST endpoints for flag management with RBAC and audit logging
- **Analytics** - Evaluation tracking, metrics, and Prometheus export
- **OpenFeature support** - Vendor-agnostic evaluation via OpenFeature SDK
- **Approval workflows** - Human-in-the-loop governance for enterprise use

## Documentation

Full docs at [flags.litestar.scriptr.dev](https://flags.litestar.scriptr.dev).

## Development

```bash
git clone https://github.com/JacobCoffee/litestar-flags.git
cd litestar-flags
uv sync --all-extras
uv run pytest
```

## License

MIT
