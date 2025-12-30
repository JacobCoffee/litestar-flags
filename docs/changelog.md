# Changelog

All notable changes to this project will be documented in this file.

## [unreleased]


### Bug Fixes


- fix: checkout main branch in CD workflow for changelog push - ([92f334a](https://github.com/JacobCoffee/litestar-flags/commit/92f334a884b4229341cea80465ae98c175d744f3)) - Jacob Coffee

- fix: explicitly set remote URL with PAT for changelog push - ([18b836a](https://github.com/JacobCoffee/litestar-flags/commit/18b836a9e99f796cdf52bd6c94b93bd20f31cb97)) - Jacob Coffee

- fix: create PR instead of direct push for changelog updates - ([ecc2469](https://github.com/JacobCoffee/litestar-flags/commit/ecc24699b179a9bafafefb9452014d6f0bc4eeb8)) - Jacob Coffee

- fix: revert to direct push for changelog - ([95c0fd1](https://github.com/JacobCoffee/litestar-flags/commit/95c0fd1c22966f410cd6ead4a8e48f3883bd2d51)) - Jacob Coffee
## [0.2.0](https://github.com/JacobCoffee/litestar-flags/compare/v0.1.1..v0.2.0) - 2025-12-30


### Bug Fixes


- fix: use text lexer instead of http for code blocks in docs

The http lexer is strict about format and was causing warnings.
Using text lexer for HTTP request examples.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([56a038b](https://github.com/JacobCoffee/litestar-flags/commit/56a038baee4d8266fb3bf6038dca3ae3c5fc6630)) - Jacob Coffee

- fix: remove On This Page ToC and fix duplicate toctree refs

- Remove .. contents:: directives from all docs pages (sidebar ToC exists)
- Fix duplicate toctree references by linking user-guide/index instead
- Remove :orphan: from user-guide/index.rst

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([2354807](https://github.com/JacobCoffee/litestar-flags/commit/235480792c948eef057a37590c2a6a0e5ee2a821)) - Jacob Coffee


### Features


- feat: add segment-based targeting for reusable user groups (#2) - ([62ae7ce](https://github.com/JacobCoffee/litestar-flags/commit/62ae7cecea2ea25de611e7e25f1fcd71e15122b8)) - Jacob Coffee

- feat: add multi-environment support with inheritance and promotion

Implements Phase 13 of the litestar-flags roadmap with full multi-environment
support for managing feature flags across dev/staging/production environments.

New features:
- Environment model with hierarchical parent-child relationships
- EnvironmentFlag model for per-environment flag overrides
- Environment inheritance (child environments inherit from parents)
- Circular inheritance detection and validation
- Flag promotion workflow (dev -> staging -> production)
- Environment middleware for automatic context extraction
- StorageBackend protocol extended with environment CRUD operations
- MemoryStorageBackend implementation of environment storage
- FeatureFlagsConfig with environment settings
- EvaluationContext.with_environment() for environment-specific evaluation
- Comprehensive test suite (98 environment tests)
- Full documentation - ([fe095f7](https://github.com/JacobCoffee/litestar-flags/commit/fe095f708e026e90f91dfb5ded9a5ef2c78d64b3)) - Jacob Coffee

- feat: add flag analytics module with evaluation tracking and metrics

Adds comprehensive analytics support for feature flag evaluations:

- FlagEvaluationEvent model with timestamp, flag_key, value, reason,
  variant, targeting_key, context_attributes, and evaluation_duration_ms
- AnalyticsCollector protocol for pluggable analytics backends
- InMemoryAnalyticsCollector for development and testing
- DatabaseAnalyticsCollector with batch writes for production persistence
- AnalyticsAggregator for computing metrics:
  - Evaluation rate (evaluations per second)
  - Unique users count
  - Variant distribution
  - Reason distribution
  - Error rate calculation
  - Latency percentiles (p50, p90, p99)
- FlagMetrics dataclass for aggregated metrics
- PrometheusExporter for Prometheus-compatible metrics
- OTelAnalyticsExporter for OpenTelemetry tracing integration
- Analytics hooks in EvaluationEngine for automatic event recording
- Comprehensive test suite (57 tests)
- User guide and API reference documentation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([026995c](https://github.com/JacobCoffee/litestar-flags/commit/026995c4c27d8be6c868a3b0f7d3222e9134debf)) - Jacob Coffee

- feat: add Admin API with REST endpoints for flag management

Implements Phase 14 - Admin API with the following features:

Controllers:
- FlagsController: CRUD endpoints for feature flags with archive/restore
- RulesController: Manage targeting rules with priority reordering
- OverridesController: Entity-specific flag overrides
- SegmentsController: User segment management with evaluation
- EnvironmentsController: Multi-environment config with inheritance
- AnalyticsController: Metrics, events, trends, and export

Supporting Modules:
- msgspec Struct DTOs for request/response schemas
- Role-based access control (RBAC) with permission guards
- Audit logging for all admin operations
- AdminPlugin for easy router registration

Tests:
- 53 comprehensive test cases covering all endpoints
- Permission guard tests for access control
- Plugin configuration tests

Documentation:
- Full Admin API usage guide with examples
- Authentication and authorization patterns
- Request/response examples

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([a9dfb20](https://github.com/JacobCoffee/litestar-flags/commit/a9dfb203ee46b7fa924a1dbfb506cc4e9667a600)) - Jacob Coffee

- feat: add CD workflow for changelog automation and update docs

- Add cd.yml workflow for automated changelog generation on release
- Update publish.yml to use git-cliff for release notes
- Add `make changelog` target to Makefile
- Update README with new features (Admin API, Analytics, Segments, Multi-env)
- Update README with missing extras (openfeature, prometheus, observability)
- Fix FeatureFlagClient class name in README
- Add new feature cards to docs index
- Add Admin API reference to API docs
- Configure git-cliff to skip non-conventional commits
- Remove duplicate CHANGELOG.md (now in docs/changelog.md)
- Bump version to 0.2.0

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([d1de4ba](https://github.com/JacobCoffee/litestar-flags/commit/d1de4babf2896c2278d5ff5789f333b8a5a5ee6a)) - Jacob Coffee


### Miscellaneous Chores


- chore: add optional deps to docs group for autodoc type resolution

Add prometheus-client, opentelemetry-api, openfeature-sdk, and structlog
to docs dependency group so sphinx-autodoc-typehints can resolve all
forward references without warnings.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([eeb82d5](https://github.com/JacobCoffee/litestar-flags/commit/eeb82d57227e68646c0da5c037ebdfb835deedfe)) - Jacob Coffee


### Refactoring


- refactor: rename AdminPlugin to FeatureFlagsAdminPlugin

Rename for clarity and consistency with FeatureFlagsPlugin:
- AdminConfig -> FeatureFlagsAdminConfig
- AdminPlugin -> FeatureFlagsAdminPlugin

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([fa97090](https://github.com/JacobCoffee/litestar-flags/commit/fa97090fc41e839e2da0c84deb358860ea1ba234)) - Jacob Coffee
## [0.1.1] - 2025-12-28


### Bug Fixes


- fix: resolve zizmor security scan findings - ([94f6c18](https://github.com/JacobCoffee/litestar-flags/commit/94f6c1814524e201f6397f8a832c555e97e7c35a)) - Jacob Coffee

- fix: remove local path override for litestar-workflows - ([e16ce98](https://github.com/JacobCoffee/litestar-flags/commit/e16ce98e43a6a276825a8a262c2a2910b38e7ecb)) - Jacob Coffee

- fix: move importlib import to top of file - ([db6ee09](https://github.com/JacobCoffee/litestar-flags/commit/db6ee094745d4444f8cfcd0815ebf9489a6ee374)) - Jacob Coffee

- fix: use longer TTL for Windows clock resolution compatibility - ([a9bb0c6](https://github.com/JacobCoffee/litestar-flags/commit/a9bb0c6aa778789c17ab1d7d49b17565fb626d32)) - Jacob Coffee

- fix: remove skip logic for otel tests - all extras should be installed - ([e09b647](https://github.com/JacobCoffee/litestar-flags/commit/e09b6479f2992202128a5b4f158e94e19419fb8b)) - Jacob Coffee

- fix: increase timeouts for Windows clock resolution

- Add asyncio.sleep before flag update in redis storage tests
- Increase recovery_timeout and sleep in circuit breaker edge case tests
- Windows has ~15ms clock resolution vs ~1ms on Unix

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([1caf061](https://github.com/JacobCoffee/litestar-flags/commit/1caf061fb291b0349d1439518c124dc5d52b8bca)) - Jacob Coffee

- fix: increase token bucket refill test sleep for Windows

Windows has ~15.6ms clock resolution, so 10ms sleep may not register.
Using 50ms ensures reliable timing across all platforms.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([30fbe99](https://github.com/JacobCoffee/litestar-flags/commit/30fbe9941f8e47d9c8fe1166f6200c85d70f99a6)) - Jacob Coffee

- fix: add missing linkify-it-py for docs build

Required by myst-parser for link processing.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([315f2fc](https://github.com/JacobCoffee/litestar-flags/commit/315f2fc08e234cfe6156cf9cdac98cfbe9dbaf07)) - Jacob Coffee

- fix: add pyproject.toml to docs workflow trigger paths

Ensures docs rebuild when dependencies change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([a1d42c3](https://github.com/JacobCoffee/litestar-flags/commit/a1d42c321aece9f58f57ba0d2566f80bff82a322)) - Jacob Coffee


### Miscellaneous Chores


- chore: add project CLAUDE.md, use prek, fix type exclusions and tests - ([868f5ff](https://github.com/JacobCoffee/litestar-flags/commit/868f5ff194b8e2698f50d49371f9da6773edac6b)) - Jacob Coffee

- chore: add git-cliff configuration and initial changelog

- Configure git-cliff for conventional commits changelog generation
- Generate initial changelog for v0.1.0

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([4d84cf6](https://github.com/JacobCoffee/litestar-flags/commit/4d84cf6ce0c69b9033e4bc2a8b15255f3d0ffe87)) - Jacob Coffee

- chore: bump version to 0.1.1

- Update CLAUDE.md with version bumping and release process docs
- Update changelog for v0.1.1

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com> - ([fe020fb](https://github.com/JacobCoffee/litestar-flags/commit/fe020fb163109cc46fb3ebf313e787522638ae6e)) - Jacob Coffee


### Style


- style: apply ruff formatting - ([1dd97ea](https://github.com/JacobCoffee/litestar-flags/commit/1dd97ea211ac6c371e639cfcb7f3d71d3c30333e)) - Jacob Coffee
---
*litestar-flags Changelog*
