How-To Guides
=============

This section contains step-by-step guides for common tasks and patterns when
working with litestar-flags.


Storage Backends
----------------

Learn how to configure different storage backends for your feature flags:

- **Memory Backend**: Fast, in-memory storage (default, great for development)
- **Redis Backend**: Distributed storage for multi-instance deployments
- **Database Backend**: Persistent storage using SQLAlchemy


Feature Management
------------------

Guides for managing feature flags in your application:

- **Percentage Rollouts**: Gradually roll out features to a percentage of users
- **User Targeting**: Enable features for specific users or groups
- **A/B Testing**: Set up experiments with multiple variants


Integration Patterns
--------------------

Best practices for integrating feature flags into your codebase:

- **Dependency Injection**: Using feature flags with Litestar's DI system
- **Middleware Integration**: Apply feature flags at the middleware level
- **Multi-Environment**: Configure flags across dev/staging/production
- **Testing**: Strategies for testing code with feature flags


.. toctree::
   :maxdepth: 2
   :hidden:

   storage-backends
   percentage-rollouts
   user-targeting
   ab-testing
   environments
   testing
