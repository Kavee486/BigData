"""Prometheus metrics exported by the serving API at GET /metrics.

Gauges that describe the pipeline (freshness, data quality, lag, business
KPIs) are refreshed from Postgres on every scrape (serving/api/main.py ->
refresh_pipeline_gauges), so Prometheus sees the pipeline's state even when
nobody is looking at the dashboard. The Prometheus alert rules in
observability/prometheus/alert_rules.yml are written against these names.
"""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

API_REQUESTS_TOTAL = Counter("api_requests_total", "Total API requests handled", ["endpoint", "status"])
API_REQUEST_SECONDS = Histogram("api_request_duration_seconds", "API request latency", ["endpoint"])

ALERTS_ACTIVE = Gauge("alerts_active", "Open (unresolved) alerts", ["alert_type"])
ZONE_RENEWABLE_PCT = Gauge("zone_renewable_pct_latest", "Latest complete-window renewable % per zone", ["grid_zone"])
ZONE_LOAD_KWH = Gauge("zone_load_kwh_latest", "Latest complete-window consumption (kWh) per zone", ["grid_zone"])
PIPELINE_COMPONENT_STALENESS_SECONDS = Gauge(
    "pipeline_component_staleness_seconds", "Seconds since last heartbeat per pipeline component", ["component"])
PIPELINE_COMPONENT_STALE_BUDGET_SECONDS = Gauge(
    "pipeline_component_stale_budget_seconds", "Allowed silence before a component is stale", ["component"])
PIPELINE_COMPONENT_UP = Gauge("pipeline_component_up", "1 if the component is fresh and OK, else 0", ["component"])
STREAM_EVENTS_5M = Gauge("stream_events_last_5m", "Speed-layer events in the last 5 minutes", ["outcome"])
STREAM_INVALID_RATE_PCT = Gauge("stream_invalid_event_rate_pct", "Quarantined share of events, last 5 minutes")
STREAM_LAG_SECONDS = Gauge("stream_processing_lag_seconds", "Avg event-time -> processing lag, recent batches")
BATCH_LAST_BILLED_DAY = Gauge("batch_last_billed_sim_day", "Most recent simulated day billed by the batch layer")
BATCH_RECONCILIATION_DRIFT_PCT = Gauge("batch_reconciliation_drift_pct", "Speed vs batch drift % for the last billed day")
BATCH_TOTAL_BILLED = Gauge("batch_total_billed_lkr", "Total billed (LKR) for the last billed day")
SIM_DAY_CURRENT = Gauge("sim_day_current", "Current simulated day number")


def render_latest():
    return generate_latest(), CONTENT_TYPE_LATEST
