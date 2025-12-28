# litestar-flags

Production-ready feature flags library for Litestar with percentage rollouts, A/B testing, user targeting, and time-based rules.

## Project Rules & Conventions

### Git & Commits

- **Atomic commits** - each commit is a logical unit of work
- **Conventional commits** - `feat:`, `fix:`, `docs:`, `chore:`, `test:`
- **Run `make ci` before committing** - lint, format, type-check, tests must pass
- **All PR checks must pass** - use `gh pr checks` or `make act-ci` to verify
  When Pull requests are made, run `gh pr view $PR_NUMBER --web` so that I can see it.
  Address all PR comments, comment on those review comments saying you fixed it with the commit
  hash

### Python & Tooling

- **Always use `uv run`** - never call `python`/`python3` directly
- **Use Makefile targets** - `make help` shows all commands
- **Ruff for linting/formatting** - `make lint`, `make fmt`
- **ty for type checking** - `make type-check`
- **PEP 649 annotations** - use `from __future__ import annotations` in all modules

### Agent Workflow

- **Dispatch subagents in parallel** - don't serialize when tasks are independent
- **Use specialized agents** - docs expert for docs, python engineer for code
- **Dispatch doc agent after code is done** - for documenting new features
- **Run `make ci` and example apps before signing off**

### CI/CD

- **zizmor for workflow security** - `make security` scans GitHub Actions
- **Pin actions to SHA hashes** - not tags (for security)
- **Add `persist-credentials: false`** to checkout steps
- **Explicit permissions** on all workflow jobs

### Testing

- **aiosqlite for async SQLite** - in-memory test database
- **Litestar TestClient** - async test client for API tests
- **PYTHONDONTWRITEBYTECODE=1** - faster test runs

### Code Standards

- **Async-first** - all execution methods must be async
- **Full type hints** - strict ty/mypy compatible
- **Google-style docstrings** - on all public APIs
- **High test coverage target** - for all modules

---

## Project Overview

- **Package**: `litestar-flags`
- **Python**: 3.11+
- **Framework**: Litestar 2.x
- **Docs**: https://flags.litestar.scriptr.dev

## Architecture

```
src/litestar_flags/
├── client.py          # FeatureFlagsClient for flag evaluation
├── config.py          # FeatureFlagsConfig settings
├── plugin.py          # Litestar plugin integration
├── engine.py          # Evaluation engine with rule processing
├── models/            # Flag, Rule, Variant, Override models
├── storage/           # Memory, Redis, Database backends
├── contrib/           # Optional integrations
│   ├── openfeature.py # OpenFeature provider
│   └── workflows/     # Approval workflow integration
└── time_rules.py      # Time-based scheduling
```

### Extras

- **Core** - In-memory storage, works without external dependencies
- **`[redis]`** - Redis storage backend for distributed deployments
- **`[database]`** - SQLAlchemy storage backend for persistence
- **`[workflows]`** - Approval workflow integration with litestar-workflows
- **`[all]`** - All optional dependencies

---

## Critical Rules

1. **ALWAYS use `uv run`** - Never call `python`/`python3` directly
2. **ALWAYS run `make ci`** before committing
3. **Keep code async-first** - All execution methods must be async
4. **Full type hints** - Strict ty/mypy compatible
5. **Google-style docstrings** - On all public APIs

---

## Development Commands

### Package Management (uv)

```bash
uv sync                    # Install dependencies
uv sync --all-extras       # Install with all extras
uv add <package>           # Add dependency
uv remove <package>        # Remove dependency
uv lock                    # Update lock file
```

### Development Workflow

```bash
make dev                   # Install dev dependencies
make ci                    # Run all checks (lint + type-check + test)
make test                  # Run tests
make test-cov              # Run tests with coverage
make lint                  # Run linters (ruff via prek)
make fmt                   # Format code
make type-check            # Run ty type checker
```

### Documentation

```bash
make docs                  # Build documentation
make docs-serve            # Serve with live reload
```

### Building

```bash
make build                 # Build package
make clean                 # Clean artifacts
```

### Version Bumping (uv 0.7+)

```bash
uv version                 # Show current version (e.g., "litestar-flags 0.1.0")
uv version --bump patch    # Bump patch version (0.1.0 => 0.1.1)
uv version --bump minor    # Bump minor version (0.1.1 => 0.2.0)
uv version --bump major    # Bump major version (0.2.0 => 1.0.0)
uv self version            # Show uv version itself
```

---

## Workflow Files

| Workflow      | Trigger        | Description                                                   |
| ------------- | -------------- | ------------------------------------------------------------- |
| `ci.yml`      | push/PR        | Lint, format, type-check, tests (OS matrix)                   |
| `docs.yml`    | push to main   | Build and deploy docs to GitHub Pages                         |
| `publish.yml` | tag push (v\*) | Build, sign, draft release, publish to PyPI, update changelog |

### Release Process (Immutable Releases)

```bash
# Bump version and push tag
uv version --bump patch           # Bump to 0.1.1
git add pyproject.toml
git commit -m "chore: bump version to 0.1.1"
git tag v0.1.1
git push origin main --tags       # CD workflow auto-triggers
```

The publish workflow:

1. Builds distribution
2. Signs with Sigstore
3. Creates draft GitHub release with assets
4. Publishes to PyPI
5. Publishes release (removes draft status)

**Important**: Releases are immutable. Once a version is tagged, it cannot be re-released. Always bump the version for new releases.

---

## Code Standards

### Imports

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar_flags import FeatureFlagsClient
```

### Flag Evaluation

```python
from litestar import get
from litestar_flags import FeatureFlagsClient

@get("/")
async def index(feature_flags: FeatureFlagsClient) -> dict:
    if await feature_flags.is_enabled("new_feature"):
        return {"feature": "enabled"}
    return {"feature": "disabled"}
```

---

## Testing

```bash
make test                           # Run all tests
make test-fast                      # Quick tests (fail fast)
uv run pytest tests/test_client.py  # Run specific file
uv run pytest -k "test_engine"      # Run by pattern
```

---

## Git Workflow

1. **Atomic commits** - One logical change per commit
2. **Conventional commits** - `feat:`, `fix:`, `docs:`, `chore:`
3. **PR checks must pass** - Use `gh pr checks` or `make act-ci` to verify
4. **Squash merge** - Keep main history clean

```bash
git add -p                          # Stage selectively
git commit -m "feat: add new storage backend"
make ci                             # Test locally first
gh pr create --fill
gh pr checks                        # Wait for CI
```

---

## Key Files

| File                         | Purpose                              |
| ---------------------------- | ------------------------------------ |
| `pyproject.toml`             | Package config, dependencies         |
| `Makefile`                   | Development commands                 |
| `src/litestar_flags/`        | Source code                          |
| `tests/`                     | Test suite                           |
| `docs/`                      | Sphinx documentation                 |
