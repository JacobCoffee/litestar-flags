Changelog
=========

All notable changes to this project will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.


[Unreleased]
------------

Added
~~~~~
- Initial release of litestar-flags
- Feature flag core functionality with ``FeatureFlag`` model
- ``FeatureFlagsPlugin`` for Litestar integration
- ``FeatureFlagsClient`` for runtime flag evaluation
- Multiple storage backends:
  - ``MemoryStorageBackend`` for in-memory storage
  - ``RedisStorageBackend`` for distributed storage
  - ``DatabaseStorageBackend`` for persistent storage with SQLAlchemy
- Percentage rollout support
- User targeting capabilities
- Comprehensive test suite
- Sphinx documentation
