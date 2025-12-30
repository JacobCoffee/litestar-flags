Flag Analytics
==============

litestar-flags provides a comprehensive analytics module for tracking and
analyzing feature flag evaluations. This enables insights into flag usage,
performance monitoring, and targeting effectiveness.


Introduction
------------

The analytics module captures every flag evaluation as an event, allowing you to:

- **Monitor Usage**: Track which flags are evaluated most frequently
- **Analyze Targeting**: Understand how users are distributed across variants
- **Debug Issues**: Identify error rates and evaluation failures
- **Optimize Performance**: Monitor evaluation latency with percentile metrics
- **Export Metrics**: Integrate with Prometheus and OpenTelemetry for observability

The module follows a collector/aggregator pattern:

1. **Collectors** capture evaluation events and store them
2. **Aggregators** compute metrics from collected events
3. **Exporters** push metrics to external monitoring systems


Core Components
---------------

FlagEvaluationEvent
~~~~~~~~~~~~~~~~~~~

The ``FlagEvaluationEvent`` dataclass captures all details of a single flag evaluation:

.. code-block:: python

   from datetime import datetime, UTC
   from litestar_flags.analytics import FlagEvaluationEvent
   from litestar_flags.types import EvaluationReason

   event = FlagEvaluationEvent(
       timestamp=datetime.now(UTC),
       flag_key="checkout_redesign",
       value=True,
       reason=EvaluationReason.TARGETING_MATCH,
       variant="treatment_a",
       targeting_key="user-12345",
       context_attributes={"plan": "premium", "country": "US"},
       evaluation_duration_ms=1.5,
   )

**Event Attributes:**

+---------------------------+--------------------------------------------------+
| Attribute                 | Description                                      |
+===========================+==================================================+
| ``timestamp``             | When the evaluation occurred (UTC)               |
+---------------------------+--------------------------------------------------+
| ``flag_key``              | The key of the evaluated flag                    |
+---------------------------+--------------------------------------------------+
| ``value``                 | The evaluated flag value (any type)              |
+---------------------------+--------------------------------------------------+
| ``reason``                | Why this value was returned (EvaluationReason)   |
+---------------------------+--------------------------------------------------+
| ``variant``               | The variant key if applicable                    |
+---------------------------+--------------------------------------------------+
| ``targeting_key``         | User/entity identifier used for targeting        |
+---------------------------+--------------------------------------------------+
| ``context_attributes``    | Additional context used in evaluation            |
+---------------------------+--------------------------------------------------+
| ``evaluation_duration_ms``| Time taken to evaluate in milliseconds           |
+---------------------------+--------------------------------------------------+

**Evaluation Reasons:**

- ``DEFAULT``: Flag returned its default value
- ``STATIC``: Flag has a static configuration
- ``TARGETING_MATCH``: A targeting rule matched
- ``OVERRIDE``: An override was applied
- ``SPLIT``: User was bucketed via percentage rollout
- ``DISABLED``: Flag is disabled
- ``ERROR``: An error occurred during evaluation


AnalyticsCollector Protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~

All collectors implement the ``AnalyticsCollector`` protocol:

.. code-block:: python

   from litestar_flags.analytics import AnalyticsCollector

   class MyCollector:
       """Custom analytics collector."""

       async def record(self, event: FlagEvaluationEvent) -> None:
           """Record a flag evaluation event."""
           # Store or process the event
           ...

       async def flush(self) -> None:
           """Flush any buffered events."""
           ...

       async def close(self) -> None:
           """Clean up resources."""
           ...


In-Memory Collector
-------------------

The ``InMemoryAnalyticsCollector`` stores events in memory with a configurable
maximum size. Ideal for development, testing, and low-volume production use.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from datetime import datetime, UTC
   from litestar_flags.analytics import (
       FlagEvaluationEvent,
       InMemoryAnalyticsCollector,
   )
   from litestar_flags.types import EvaluationReason

   # Create collector with max 10,000 events
   collector = InMemoryAnalyticsCollector(max_size=10000)

   # Record an evaluation event
   event = FlagEvaluationEvent(
       timestamp=datetime.now(UTC),
       flag_key="dark_mode",
       value=True,
       reason=EvaluationReason.STATIC,
       targeting_key="user-123",
   )
   await collector.record(event)

   # Retrieve stored events
   events = await collector.get_events()
   print(f"Recorded {len(events)} events")

   # Filter by flag key
   dark_mode_events = await collector.get_events(flag_key="dark_mode")

   # Get most recent events with limit
   recent = await collector.get_events(limit=100)

   # Clean up
   await collector.close()

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   collector = InMemoryAnalyticsCollector(
       max_size=10000,  # Maximum events to store (default: 10000)
   )

When the maximum size is reached, oldest events are automatically discarded
to make room for new ones (FIFO behavior).

Utility Methods
~~~~~~~~~~~~~~~

.. code-block:: python

   # Get event count
   total = await collector.get_event_count()
   flag_count = await collector.get_event_count(flag_key="my_flag")

   # Clear all events without closing
   await collector.clear()

   # Check current size (not thread-safe, use get_event_count for accuracy)
   size = len(collector)


Database Collector
------------------

The ``DatabaseAnalyticsCollector`` persists events to a database using
SQLAlchemy async sessions. Features batch writes for optimal performance.

.. note::

   Requires the ``database`` extra: ``pip install litestar-flags[database]``

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.analytics.collectors.database import DatabaseAnalyticsCollector

   # Create collector with factory method
   collector = await DatabaseAnalyticsCollector.create(
       connection_string="postgresql+asyncpg://user:pass@localhost/analytics",
       batch_size=100,
       flush_interval_seconds=5.0,
       create_tables=True,  # Auto-create analytics_events table
   )

   try:
       # Record events (batched automatically)
       await collector.record(event)

       # Force immediate flush
       await collector.flush()
   finally:
       # Clean up (flushes remaining events)
       await collector.close()

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   collector = await DatabaseAnalyticsCollector.create(
       connection_string="postgresql+asyncpg://user:pass@localhost/db",
       batch_size=100,           # Events buffered before auto-flush
       flush_interval_seconds=5.0,  # Seconds between periodic flushes
       create_tables=True,       # Create tables on startup
       echo=False,               # SQLAlchemy engine echo setting
   )

**Connection String Examples:**

- PostgreSQL: ``postgresql+asyncpg://user:pass@host/db``
- SQLite: ``sqlite+aiosqlite:///analytics.db``
- MySQL: ``mysql+aiomysql://user:pass@host/db``

Health Monitoring
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Check database connectivity
   is_healthy = await collector.health_check()
   if not is_healthy:
       print("Database connection issue!")

   # Check buffer status
   buffer_size = await collector.get_buffer_size()
   print(f"Events pending flush: {buffer_size}")


Analytics Aggregator
--------------------

The ``AnalyticsAggregator`` computes metrics from collected events.
Supports both in-memory collectors and database sessions as data sources.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.analytics import (
       AnalyticsAggregator,
       InMemoryAnalyticsCollector,
   )

   collector = InMemoryAnalyticsCollector()
   aggregator = AnalyticsAggregator(collector)

   # After recording some events...

   # Get evaluation rate (evaluations per second)
   rate = await aggregator.get_evaluation_rate(
       flag_key="my_flag",
       window_seconds=60,  # Last minute
   )
   print(f"Evaluation rate: {rate:.2f}/s")

   # Get unique users
   users = await aggregator.get_unique_users(
       flag_key="my_flag",
       window_seconds=3600,  # Last hour
   )
   print(f"Unique users: {users}")

   # Get variant distribution
   distribution = await aggregator.get_variant_distribution("ab_test")
   # {"control": 1000, "treatment_a": 500, "treatment_b": 500}

   # Get reason distribution
   reasons = await aggregator.get_reason_distribution("my_flag")
   # {"TARGETING_MATCH": 800, "SPLIT": 150, "DEFAULT": 50}

   # Get error rate (percentage)
   error_rate = await aggregator.get_error_rate("my_flag")
   print(f"Error rate: {error_rate:.2f}%")

   # Get latency percentiles
   latencies = await aggregator.get_latency_percentiles("my_flag")
   # {50.0: 1.2, 90.0: 2.5, 99.0: 5.0}

Complete Metrics
~~~~~~~~~~~~~~~~

Use ``get_flag_metrics()`` to retrieve all metrics in a single call:

.. code-block:: python

   metrics = await aggregator.get_flag_metrics(
       flag_key="my_flag",
       window_seconds=3600,  # Analysis window
   )

   print(f"Evaluation rate: {metrics.evaluation_rate}/s")
   print(f"Total evaluations: {metrics.total_evaluations}")
   print(f"Unique users: {metrics.unique_users}")
   print(f"Error rate: {metrics.error_rate}%")
   print(f"P50 latency: {metrics.latency_p50}ms")
   print(f"P90 latency: {metrics.latency_p90}ms")
   print(f"P99 latency: {metrics.latency_p99}ms")
   print(f"Variant distribution: {metrics.variant_distribution}")
   print(f"Reason distribution: {metrics.reason_distribution}")
   print(f"Window: {metrics.window_start} to {metrics.window_end}")


FlagMetrics
~~~~~~~~~~~

The ``FlagMetrics`` dataclass contains all aggregated statistics:

+---------------------------+--------------------------------------------------+
| Attribute                 | Description                                      |
+===========================+==================================================+
| ``evaluation_rate``       | Evaluations per second in the window             |
+---------------------------+--------------------------------------------------+
| ``total_evaluations``     | Total evaluation count                           |
+---------------------------+--------------------------------------------------+
| ``unique_users``          | Count of unique targeting keys                   |
+---------------------------+--------------------------------------------------+
| ``variant_distribution``  | Dict mapping variant names to counts             |
+---------------------------+--------------------------------------------------+
| ``reason_distribution``   | Dict mapping reasons to counts                   |
+---------------------------+--------------------------------------------------+
| ``error_rate``            | Percentage of ERROR evaluations (0-100)          |
+---------------------------+--------------------------------------------------+
| ``latency_p50``           | 50th percentile latency in ms                    |
+---------------------------+--------------------------------------------------+
| ``latency_p90``           | 90th percentile latency in ms                    |
+---------------------------+--------------------------------------------------+
| ``latency_p99``           | 99th percentile latency in ms                    |
+---------------------------+--------------------------------------------------+
| ``window_start``          | Start of the measurement window                  |
+---------------------------+--------------------------------------------------+
| ``window_end``            | End of the measurement window                    |
+---------------------------+--------------------------------------------------+

Using with Database Sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For database-backed analytics, pass an ``AsyncSession`` to the aggregator:

.. code-block:: python

   from sqlalchemy.ext.asyncio import AsyncSession

   async def get_metrics(session: AsyncSession, flag_key: str):
       aggregator = AnalyticsAggregator(session)
       metrics = await aggregator.get_flag_metrics(flag_key)
       return metrics


Prometheus Integration
----------------------

The ``PrometheusExporter`` exposes feature flag metrics in Prometheus format
for monitoring and alerting.

.. note::

   Requires ``prometheus_client``: ``pip install prometheus_client``

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.analytics import PrometheusExporter

   # Create exporter with default registry
   exporter = PrometheusExporter()

   # Record evaluation events
   await exporter.record(event)

   # Metrics are automatically exposed via prometheus_client

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   from prometheus_client import CollectorRegistry

   # Custom registry for testing or isolation
   registry = CollectorRegistry()

   exporter = PrometheusExporter(
       registry=registry,
       prefix="myapp",  # Metric prefix: myapp_feature_flag_*
       duration_buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1),
   )

Exposed Metrics
~~~~~~~~~~~~~~~

The exporter creates the following Prometheus metrics:

**Counters:**

- ``feature_flag_evaluations_total``: Total flag evaluations
  - Labels: ``flag_key``, ``reason``, ``variant``

**Histograms:**

- ``feature_flag_evaluation_duration_seconds``: Evaluation duration
  - Labels: ``flag_key``
  - Default buckets: 100us to 1s

**Gauges:**

- ``feature_flag_unique_users``: Unique users per flag
  - Labels: ``flag_key``

- ``feature_flag_error_rate``: Error rate (0.0 to 1.0)
  - Labels: ``flag_key``

Syncing from Aggregator
~~~~~~~~~~~~~~~~~~~~~~~

Update gauges from pre-computed aggregator metrics:

.. code-block:: python

   from litestar_flags.analytics import AnalyticsAggregator, PrometheusExporter

   collector = InMemoryAnalyticsCollector()
   aggregator = AnalyticsAggregator(collector)
   exporter = PrometheusExporter()

   # Update gauges from aggregator periodically
   await exporter.update_from_aggregator(
       aggregator=aggregator,
       flag_keys=["feature_a", "feature_b", "ab_test"],
       window_seconds=3600,
   )

   # Or update from a single FlagMetrics object
   metrics = await aggregator.get_flag_metrics("my_flag")
   exporter.update_from_metrics("my_flag", metrics)

Litestar Integration
~~~~~~~~~~~~~~~~~~~~

Expose Prometheus metrics endpoint in your Litestar application:

.. code-block:: python

   from litestar import Litestar, get
   from litestar.response import Response
   from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

   @get("/metrics")
   async def metrics() -> Response:
       """Prometheus metrics endpoint."""
       return Response(
           content=generate_latest(),
           media_type=CONTENT_TYPE_LATEST,
       )

   app = Litestar(route_handlers=[metrics])


OpenTelemetry Integration
-------------------------

The ``OTelAnalyticsExporter`` exports analytics as OpenTelemetry spans and
metrics for distributed tracing and observability.

.. note::

   Requires ``opentelemetry-api``: ``pip install opentelemetry-api``

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from litestar_flags.analytics.exporters.otel import OTelAnalyticsExporter

   # Create exporter with automatic batching
   exporter = OTelAnalyticsExporter(
       batch_size=100,
       flush_interval=30.0,
   )

   # Record evaluation events
   await exporter.record(event)

   # Clean up
   await exporter.close()

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   from opentelemetry import trace, metrics

   # Use custom tracer and meter
   tracer = trace.get_tracer("my-app")
   meter = metrics.get_meter("my-app")

   exporter = OTelAnalyticsExporter(
       tracer=tracer,
       meter=meter,
       batch_size=50,           # Events per batch (0 to disable)
       flush_interval=10.0,     # Seconds between flushes (0 to disable)
       record_values=False,     # Privacy: don't record flag values
       create_spans=True,       # Create spans for each event
   )

Sharing with OTelHook
~~~~~~~~~~~~~~~~~~~~~

If you're using the ``OTelHook`` for flag evaluation tracing, share the
tracer and meter for consistent instrumentation:

.. code-block:: python

   from litestar_flags.contrib.otel import OTelHook
   from litestar_flags.analytics.exporters.otel import (
       OTelAnalyticsExporter,
       create_exporter_from_hook,
   )

   # Create the evaluation hook
   hook = OTelHook()

   # Create analytics exporter sharing the same instruments
   exporter = create_exporter_from_hook(
       otel_hook=hook,
       batch_size=100,
       record_values=False,
   )

   # Or manually:
   exporter = OTelAnalyticsExporter(otel_hook=hook)

Span Attributes
~~~~~~~~~~~~~~~

Each analytics event span includes:

+------------------------------------------+------------------------------------------+
| Attribute                                | Description                              |
+==========================================+==========================================+
| ``feature_flag.key``                     | The flag key                             |
+------------------------------------------+------------------------------------------+
| ``feature_flag.reason``                  | Evaluation reason                        |
+------------------------------------------+------------------------------------------+
| ``feature_flag.variant``                 | Variant key (if applicable)              |
+------------------------------------------+------------------------------------------+
| ``feature_flag.targeting_key``           | Targeting key (if provided)              |
+------------------------------------------+------------------------------------------+
| ``feature_flag.event_timestamp``         | When the evaluation occurred             |
+------------------------------------------+------------------------------------------+
| ``feature_flag.evaluation_duration_ms``  | Evaluation latency in milliseconds       |
+------------------------------------------+------------------------------------------+

Metrics
~~~~~~~

**Counters:**

- ``feature_flag.analytics.events_recorded``: Number of recorded events
  - Labels: ``feature_flag.key``, ``feature_flag.reason``

**Histograms:**

- ``feature_flag.analytics.batch_size``: Size of event batches when flushed


Best Practices
--------------

Choosing a Collector
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Collector
     - Use When
     - Trade-offs
   * - InMemory
     - Development, testing, single-instance apps
     - Lost on restart, memory bound
   * - Database
     - Persistence required, compliance, debugging
     - Higher latency, storage costs

Batching Configuration
~~~~~~~~~~~~~~~~~~~~~~

For the database collector, tune batch settings based on your workload:

**High-volume (>1000 evals/sec):**

.. code-block:: python

   collector = await DatabaseAnalyticsCollector.create(
       connection_string="...",
       batch_size=500,
       flush_interval_seconds=1.0,
   )

**Low-latency requirements:**

.. code-block:: python

   collector = await DatabaseAnalyticsCollector.create(
       connection_string="...",
       batch_size=10,
       flush_interval_seconds=0.5,
   )

Memory Management
~~~~~~~~~~~~~~~~~

For in-memory collectors, set appropriate limits:

.. code-block:: python

   # Calculate based on expected traffic and retention
   # 100 evals/sec * 60 seconds * 10 minutes = 60,000 events
   collector = InMemoryAnalyticsCollector(max_size=60000)

Graceful Shutdown
~~~~~~~~~~~~~~~~~

Always close collectors to flush remaining events:

.. code-block:: python

   from contextlib import asynccontextmanager

   @asynccontextmanager
   async def lifespan(app):
       # Create collector
       collector = await DatabaseAnalyticsCollector.create(...)
       app.state.analytics_collector = collector
       yield
       # Flush and close on shutdown
       await collector.close()

Privacy Considerations
~~~~~~~~~~~~~~~~~~~~~~

Be mindful of what data you include in analytics:

.. code-block:: python

   # Anonymize targeting keys for privacy
   import hashlib

   def anonymize_key(user_id: str) -> str:
       return hashlib.sha256(user_id.encode()).hexdigest()[:16]

   event = FlagEvaluationEvent(
       timestamp=datetime.now(UTC),
       flag_key="my_flag",
       value=True,
       reason=EvaluationReason.STATIC,
       targeting_key=anonymize_key(user.id),
       context_attributes={},  # Omit sensitive attributes
   )

For OpenTelemetry, disable value recording:

.. code-block:: python

   exporter = OTelAnalyticsExporter(record_values=False)


See Also
--------

- :doc:`/getting-started/quickstart` - Getting started with litestar-flags
- :doc:`/guides/index` - How-to guides for common tasks
- :doc:`/api/index` - Complete API reference
