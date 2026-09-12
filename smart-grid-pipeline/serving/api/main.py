"""Serving layer: FastAPI.

Answers the business question end to end:
  "What is the current grid load and renewable contribution by zone, and
   what will each household's bill look like once daily tariff data is
   applied to their consumption?"

- /api/grid/live         -> real-time view, sourced from the speed layer's
                             live_zone_metrics table.
- /api/alerts             -> open alerts from the observability layer.
- /api/billing/daily      -> the batch layer's consolidated daily billing
                             report (optionally filtered by sim_day).
- /health                 -> liveness + pipeline freshness check.
- /metrics                -> Prometheus scrape endpoint.

This one API therefore merges the Lambda architecture's speed view and
batch view at query time, which is the standard Lambda "merge layer".
"""
import sys
import time

sys.path.append("/app")
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from config import NO_DATA_ALERT_MINUTES
from observability.logging_config import get_logger, log_event
from observability.metrics import (
    API_REQUESTS_TOTAL, ALERTS_ACTIVE, ZONE_RENEWABLE_PCT,
    PIPELINE_COMPONENT_STALENESS_SECONDS, render_latest,
)
from serving.api.db import query

logger = get_logger("serving_api")

app = FastAPI(title="Smart Grid Monitoring & Billing API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def log_and_count_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    API_REQUESTS_TOTAL.labels(endpoint=request.url.path).inc()
    log_event(
        logger, "info", "request_handled",
        path=request.url.path, status=response.status_code,
        duration_ms=round((time.time() - start) * 1000, 1),
    )
    return response


@app.get("/health")
def health():
    rows = query("SELECT component, last_heartbeat, EXTRACT(EPOCH FROM (now() - last_heartbeat)) AS age_seconds FROM pipeline_health;")
    components = {}
    overall = "OK"
    for r in rows:
        age = float(r["age_seconds"])
        status = "OK" if age < NO_DATA_ALERT_MINUTES * 60 else "STALE"
        if status != "OK":
            overall = "DEGRADED"
        components[r["component"]] = {"age_seconds": round(age, 1), "status": status}
        PIPELINE_COMPONENT_STALENESS_SECONDS.labels(component=r["component"]).set(age)
    return {"status": overall, "components": components}


@app.get("/metrics")
def metrics():
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)


@app.get("/api/grid/live")
def grid_live():
    """Real-time zone-level load & renewable mix (speed layer view)."""
    rows = query(
        """
        SELECT DISTINCT ON (grid_zone)
            grid_zone, window_start, window_end, avg_consumption_kwh,
            avg_solar_kwh, total_consumption_kwh, total_solar_kwh,
            renewable_pct, event_count, updated_at
        FROM live_zone_metrics
        ORDER BY grid_zone, window_start DESC;
        """
    )
    for r in rows:
        ZONE_RENEWABLE_PCT.labels(grid_zone=r["grid_zone"]).set(float(r["renewable_pct"]))

    total_consumption = sum(float(r["total_consumption_kwh"]) for r in rows)
    total_solar = sum(float(r["total_solar_kwh"]) for r in rows)
    overall_renewable_pct = (
        100.0 * total_solar / (total_consumption + total_solar) if (total_consumption + total_solar) > 0 else 0.0
    )
    return {
        "zones": rows,
        "grid_total_consumption_kwh": round(total_consumption, 3),
        "grid_total_solar_kwh": round(total_solar, 3),
        "grid_renewable_pct": round(overall_renewable_pct, 2),
    }


@app.get("/api/alerts")
def alerts(resolved: bool = False, limit: int = 50):
    rows = query(
        """
        SELECT id, alert_type, scope, severity, message, metric_value, threshold, triggered_at, resolved
        FROM alerts WHERE resolved = %s
        ORDER BY triggered_at DESC LIMIT %s;
        """,
        (resolved, limit),
    )
    ALERTS_ACTIVE.set(len([r for r in rows if not r["resolved"]]))
    return {"count": len(rows), "alerts": rows}


@app.get("/api/billing/daily")
def billing_daily(sim_day: int | None = Query(default=None), household_id: str | None = None):
    """Consolidated daily billing report (batch layer view)."""
    sql = "SELECT * FROM daily_billing_report WHERE 1=1"
    params = []
    if sim_day is not None:
        sql += " AND sim_day = %s"
        params.append(sim_day)
    if household_id is not None:
        sql += " AND household_id = %s"
        params.append(household_id)
    if sim_day is None:
        sql += " AND sim_day = (SELECT COALESCE(MAX(sim_day), 0) FROM daily_billing_report)"
    sql += " ORDER BY household_id;"
    rows = query(sql, tuple(params))
    total_bill = sum(float(r["bill_amount"]) for r in rows)
    return {"count": len(rows), "total_billed": round(total_bill, 2), "rows": rows}


@app.get("/api/billing/summary")
def billing_summary():
    """Per-zone billing summary for the latest available sim_day."""
    rows = query(
        """
        SELECT grid_zone,
               COUNT(*) AS households,
               ROUND(SUM(total_consumption_kwh)::numeric, 2) AS total_consumption_kwh,
               ROUND(SUM(total_solar_kwh)::numeric, 2) AS total_solar_kwh,
               ROUND(SUM(bill_amount)::numeric, 2) AS total_billed
        FROM daily_billing_report
        WHERE sim_day = (SELECT COALESCE(MAX(sim_day), 0) FROM daily_billing_report)
        GROUP BY grid_zone ORDER BY grid_zone;
        """
    )
    return {"zones": rows}


app.mount("/", StaticFiles(directory="/app/serving/dashboard", html=True), name="dashboard")
