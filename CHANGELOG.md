# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2024-12-28

### Added

- **Core Feature Flag System**
  - `FeatureFlagClient` for evaluating feature flags with type-safe methods
  - `EvaluationContext` for passing targeting attributes during evaluation
  - `EvaluationDetails` for detailed evaluation results including reason and metadata
  - Support for boolean, string, number, and object flag types

- **Storage Backends**
  - `MemoryStorageBackend` for development and testing
  - `DatabaseStorageBackend` with Advanced-Alchemy for persistent storage
  - `RedisStorageBackend` for distributed deployments
  - `StorageBackend` protocol for custom implementations

- **Targeting and Rules**
  - `FlagRule` model for conditional targeting
  - Rich set of operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `matches`
  - Percentage rollouts using consistent Murmur3 hashing
  - Entity overrides for user/organization-specific values

- **A/B Testing**
  - `FlagVariant` model for multivariate experiments
  - Weighted variant distribution
  - Consistent variant assignment per targeting key

- **Litestar Integration**
  - `FeatureFlagsPlugin` for seamless Litestar integration
  - `FeatureFlagsConfig` for centralized configuration
  - Dependency injection support for `FeatureFlagClient`
  - `FeatureFlagsMiddleware` for automatic context extraction

- **Decorators**
  - `@feature_flag` for conditional feature gating
  - `@require_flag` for access control with 403 response

- **Developer Experience**
  - Full type hints throughout the codebase
  - Never-throw evaluation pattern (always returns a value)
  - Comprehensive documentation with Sphinx
  - Examples for common use cases

### Technical Details

- Requires Python 3.11+
- Requires Litestar 2.0+
- Optional dependencies for database (Advanced-Alchemy, SQLAlchemy) and Redis backends

[Unreleased]: https://github.com/JacobCoffee/litestar-flags/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/JacobCoffee/litestar-flags/releases/tag/v0.1.0
