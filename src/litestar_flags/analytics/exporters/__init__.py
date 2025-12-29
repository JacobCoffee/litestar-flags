"""Analytics exporters for feature flag metrics.

This module provides exporters that convert analytics data to various
formats for external monitoring and observability systems.

Available exporters:
    - PrometheusExporter: Exports metrics in Prometheus format (requires [prometheus] extra)
    - OTelAnalyticsExporter: Exports analytics as OpenTelemetry spans/metrics (requires [otel] extra)

"""

from __future__ import annotations

__all__: list[str] = []

# Conditionally export PrometheusExporter
try:
    from litestar_flags.analytics.exporters.prometheus import (  # noqa: F401
        PROMETHEUS_AVAILABLE,
        PrometheusExporter,
    )

    __all__.extend(["PROMETHEUS_AVAILABLE", "PrometheusExporter"])
except ImportError:
    PROMETHEUS_AVAILABLE = False
    __all__.append("PROMETHEUS_AVAILABLE")

# Conditionally export OTelAnalyticsExporter
try:
    from litestar_flags.analytics.exporters.otel import (  # noqa: F401
        OTEL_AVAILABLE,
        OTelAnalyticsExporter,
        create_exporter_from_hook,
    )

    __all__.extend(["OTEL_AVAILABLE", "OTelAnalyticsExporter", "create_exporter_from_hook"])
except ImportError:
    OTEL_AVAILABLE = False
    __all__.append("OTEL_AVAILABLE")
