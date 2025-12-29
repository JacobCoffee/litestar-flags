API Reference
=============

Complete API documentation for litestar-flags. This reference covers all public
classes, functions, and types available in the library.

.. tip::

   For getting started guides and tutorials, see the :doc:`/getting-started/index`
   section. This reference is intended for detailed API lookups.


Core Components
---------------

The main components you will use most frequently:

- :doc:`client` - The ``FeatureFlagClient`` for evaluating feature flags
- :doc:`config` - Configuration and plugin setup
- :doc:`context` - The ``EvaluationContext`` for targeting rules


Decorators
----------

Convenient decorators for protecting route handlers:

- :doc:`decorators` - ``@feature_flag`` and ``@require_flag`` decorators


Storage Backends
----------------

Available storage backend implementations:

- :doc:`storage` - Memory, database, and Redis storage backends


Types and Enums
---------------

Type definitions and enumerations:

- :doc:`types` - Flag types, status, operators, and evaluation reasons


Exceptions
----------

Exception classes for error handling:

- :doc:`exceptions` - Error classes for feature flag operations


Models
------

Data models for flags, rules, and variants:

- :doc:`models` - ``FeatureFlag``, ``FlagRule``, ``FlagVariant``, and more


Analytics
---------

Analytics and observability components:

- :doc:`analytics` - Event models, collectors, aggregators, and exporters


.. toctree::
   :maxdepth: 2
   :hidden:

   client
   context
   config
   models
   storage
   decorators
   types
   exceptions
   analytics
