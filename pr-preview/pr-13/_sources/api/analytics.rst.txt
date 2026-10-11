Analytics
=========

The analytics module provides comprehensive tracking and analysis of feature flag
evaluations. It includes event models, collectors for storing events, aggregators
for computing metrics, and exporters for monitoring systems.

Overview
--------

The analytics system follows a three-layer architecture:

1. **Events**: ``FlagEvaluationEvent`` captures each flag evaluation
2. **Collectors**: Store events (in-memory, database, or custom backends)
3. **Aggregators**: Compute metrics from collected events
4. **Exporters**: Push metrics to external systems (Prometheus, OpenTelemetry)

For usage guides and examples, see :doc:`/user-guide/analytics`.


Core API
--------

FlagEvaluationEvent
~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.FlagEvaluationEvent
   :members:
   :undoc-members:
   :show-inheritance:


FlagMetrics
~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.FlagMetrics
   :members:
   :undoc-members:
   :show-inheritance:


AnalyticsCollector Protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.AnalyticsCollector
   :members:
   :undoc-members:
   :show-inheritance:


Collectors
----------

InMemoryAnalyticsCollector
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.InMemoryAnalyticsCollector
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


DatabaseAnalyticsCollector
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.collectors.database.DatabaseAnalyticsCollector
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


Aggregator
----------

AnalyticsAggregator
~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.AnalyticsAggregator
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


Exporters
---------

PrometheusExporter
~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.PrometheusExporter
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


OTelAnalyticsExporter
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.exporters.otel.OTelAnalyticsExporter
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


Helper Functions
~~~~~~~~~~~~~~~~

.. autofunction:: litestar_flags.analytics.exporters.otel.create_exporter_from_hook


Database Models
---------------

AnalyticsEventModel
~~~~~~~~~~~~~~~~~~~

.. autoclass:: litestar_flags.analytics.models.AnalyticsEventModel
   :members:
   :undoc-members:
   :show-inheritance:


Constants
---------

Availability Flags
~~~~~~~~~~~~~~~~~~

.. py:data:: litestar_flags.analytics.PROMETHEUS_AVAILABLE

   Boolean indicating if ``prometheus_client`` is installed and available.

.. py:data:: litestar_flags.analytics.exporters.otel.OTEL_AVAILABLE

   Boolean indicating if ``opentelemetry-api`` is installed and available.


See Also
--------

- :doc:`/user-guide/analytics` - User guide with examples
- :doc:`types` - ``EvaluationReason`` enum and other types
- :doc:`models` - Flag and rule models
