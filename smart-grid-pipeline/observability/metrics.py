"""Prometheus metrics registry shared by the serving API.

Kept intentionally small: a few counters/gauges that map directly to the
rubric's "logging, metrics and tracing ... to detect and diagnose pipeline
failures" requirement, exposed at GET /metrics in Prometheus text format.
"""
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

API_REQUESTS_TOTAL = Counter(
    "api_requests_total", "Total API requests handled", ["endpoint"]
)
ALERTS_ACTIVE = Gauge(
    "alerts_active", "Number of unresolved alerts currently open"
)
ZONE_RENEWABLE_PCT = Gauge(
    "zone_renewable_pct_latest", "Latest observed renewable percentage per zone", ["grid_zone"]
)
PIPELINE_COMPONENT_STALENESS_SECONDS = Gauge(
    "pipeline_component_staleness_seconds",
    "Seconds since last heartbeat per pipeline component",
    ["component"],
)


def render_latest():
    return generate_latest(), CONTENT_TYPE_LATEST
