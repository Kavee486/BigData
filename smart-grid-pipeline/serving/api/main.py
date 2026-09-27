"""Serving layer: FastAPI over the Postgres serving store.

Answers the business question end to end:
  "What is the current grid load and renewable contribution by zone, and what
   will each household's bill look like once daily tariff data is applied to
   their consumption?"

Speed view (real time, approximate)
  GET /api/grid/live            latest complete window per zone + grid totals
  GET /api/grid/history         per-zone time series (dashboard chart)
  GET /api/households/live      today's running consumption per household
Batch view (exact, per finished simulated day)
  GET /api/billing/daily        consolidated per-household billing report
  GET /api/billing/summary      per-zone roll-up of a billed day
  GET /api/billing/days         list of billed days with totals
  GET /api/reconciliation       speed-vs-batch drift and data-quality counters
Lambda merge (speed + batch combined at query time)
  GET /api/billing/projection   provisional bill for the running day: speed-
                                layer consumption x latest batch-validated
                                tariff, next to the last finalized bill
Observability
  GET /api/alerts, /api/pipeline/status, /health, /metrics (Prometheus)
"""
import os
import sys
import time

sys.path.append("/app")
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from common.sim_clock import day_fraction_at, get_sim_epoch, is_daylight, sim_day_at
from config import (
    COMPONENT_STALE_AFTER_SECONDS, DAYLIGHT_END_FRACTION, DAYLIGHT_START_FRACTION,
    LOW_RENEWABLE_PCT_THRESHOLD, SIMULATED_DAY_SECONDS, stale_after_seconds,
)
from observability import metrics as M
from observability.logging_config import get_logger, log_event
from processing.billing_rules import compute_bill, net_consumption_kwh, solar_contribution_pct
from serving.api.db import query

logger = get_logger("serving_api")

app = FastAPI(
    title="Smart Grid Monitoring & Billing API",
    version="2.0",
    description="Lambda-architecture serving layer: real-time grid view (speed layer), "
                "daily billing (batch layer) and their query-time merge.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def log_and_count_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - turn DB outages into a logged 503, not a crash
        log_event(logger, "error", "request_failed", path=request.url.path, error=str(exc))
        response = JSONResponse({"detail": "serving store unavailable", "error": str(exc)}, status_code=503)
    route = request.scope.get("route")
    endpoint = getattr(route, "path", "static")  # route template keeps label cardinality bounded
    duration = time.time() - start
    M.API_REQUESTS_TOTAL.labels(endpoint=endpoint, status=str(response.status_code)).inc()
    M.API_REQUEST_SECONDS.labels(endpoint=endpoint).observe(duration)
    if endpoint != "static":
        log_event(logger, "info", "request_handled", path=request.url.path, status=response.status_code,
                  duration_ms=round(duration * 1000, 1))
    return response


def _clock():
    epoch = get_sim_epoch()
    now = time.time()
    fraction = day_fraction_at(now, epoch)
    return {
        "sim_day": sim_day_at(now, epoch),
        "day_fraction": round(fraction, 3),
        "sim_time_of_day": f"{int(fraction * 24):02d}:{int((fraction * 24 % 1) * 60):02d}",
        "daylight": is_daylight(fraction, DAYLIGHT_START_FRACTION, DAYLIGHT_END_FRACTION),
        "simulated_day_seconds": SIMULATED_DAY_SECONDS,
    }


def _components():
    rows = query("SELECT component, status, detail, last_heartbeat, "
                 "EXTRACT(EPOCH FROM (now() - last_heartbeat)) AS age_seconds FROM pipeline_health "
                 "ORDER BY component;")
    out = {}
    for r in rows:
        age = float(r["age_seconds"])
        budget = stale_after_seconds(r["component"])
        state = "FAILED" if r["status"] != "OK" else ("STALE" if age > budget else "OK")
        out[r["component"]] = {"status": state, "age_seconds": round(age, 1), "stale_after_seconds": budget,
                               "detail": r["detail"], "last_heartbeat": r["last_heartbeat"]}
    return out


# ---------------------------------------------------------------------------
# Health & metrics
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    components = _components()
    expected = set(COMPONENT_STALE_AFTER_SECONDS) - {"batch_layer"}  # batch only reports after its first run
    missing = sorted(expected - set(components))
    overall = "OK" if all(c["status"] == "OK" for c in components.values()) and not missing else "DEGRADED"
    return {"status": overall, "components": components, "not_reported_yet": missing, "clock": _clock()}


def refresh_pipeline_gauges():
    for name, c in _components().items():
        M.PIPELINE_COMPONENT_STALENESS_SECONDS.labels(component=name).set(c["age_seconds"])
        M.PIPELINE_COMPONENT_STALE_BUDGET_SECONDS.labels(component=name).set(c["stale_after_seconds"])
        M.PIPELINE_COMPONENT_UP.labels(component=name).set(1 if c["status"] == "OK" else 0)
    for z in _latest_zone_windows():
        M.ZONE_RENEWABLE_PCT.labels(grid_zone=z["grid_zone"]).set(float(z["renewable_pct"]))
        M.ZONE_LOAD_KWH.labels(grid_zone=z["grid_zone"]).set(float(z["total_consumption_kwh"]))
    M.ALERTS_ACTIVE.clear()
    for r in query("SELECT alert_type, COUNT(*) AS n FROM alerts WHERE NOT resolved GROUP BY alert_type;"):
        M.ALERTS_ACTIVE.labels(alert_type=r["alert_type"]).set(r["n"])
    q = _stream_quality()
    M.STREAM_EVENTS_5M.labels(outcome="clean").set(q["clean_events"])
    M.STREAM_EVENTS_5M.labels(outcome="invalid").set(q["invalid_events"])
    M.STREAM_EVENTS_5M.labels(outcome="duplicate").set(q["duplicate_events"])
    M.STREAM_INVALID_RATE_PCT.set(q["invalid_rate_pct"])
    if q["avg_lag_seconds"] is not None:
        M.STREAM_LAG_SECONDS.set(q["avg_lag_seconds"])
    rec = query("SELECT sim_day, drift_pct, total_billed FROM batch_reconciliation ORDER BY sim_day DESC LIMIT 1;")
    if rec:
        M.BATCH_LAST_BILLED_DAY.set(rec[0]["sim_day"])
        M.BATCH_RECONCILIATION_DRIFT_PCT.set(rec[0]["drift_pct"] or 0)
        M.BATCH_TOTAL_BILLED.set(rec[0]["total_billed"] or 0)
    M.SIM_DAY_CURRENT.set(_clock()["sim_day"])


@app.get("/metrics")
def metrics():
    try:
        refresh_pipeline_gauges()
    except Exception as exc:  # noqa: BLE001 - still serve process metrics if the DB is down
        log_event(logger, "error", "metrics_refresh_failed", error=str(exc))
    body, content_type = M.render_latest()
    return Response(content=body, media_type=content_type)


# ---------------------------------------------------------------------------
# Speed view
# ---------------------------------------------------------------------------
def _latest_zone_windows():
    # Latest COMPLETE window per zone (a still-open window only holds a few
    # seconds of data and would under-report load); fall back to the newest
    # window if none has closed yet.
    return query(
        """
        SELECT DISTINCT ON (grid_zone)
            grid_zone, window_start, window_end, avg_consumption_kwh, avg_solar_kwh,
            total_consumption_kwh, total_solar_kwh, renewable_pct, event_count, household_count, updated_at
        FROM live_zone_metrics
        ORDER BY grid_zone, (window_end <= now()) DESC, window_start DESC;
        """
    )


@app.get("/api/grid/live")
def grid_live():
    """Real-time zone-level load & renewable mix (speed layer view)."""
    rows = _latest_zone_windows()
    total_consumption = sum(float(r["total_consumption_kwh"]) for r in rows)
    total_solar = sum(float(r["total_solar_kwh"]) for r in rows)
    clock = _clock()
    for r in rows:
        # below_threshold is the raw comparison; low_renewable mirrors the alert
        # rule, which only applies in simulated daylight (0% solar at night is normal).
        r["below_threshold"] = float(r["renewable_pct"]) < LOW_RENEWABLE_PCT_THRESHOLD
        r["low_renewable"] = r["below_threshold"] and clock["daylight"]
    renewable = min(100.0, 100.0 * total_solar / total_consumption) if total_consumption > 0 else 0.0
    return {
        "source": "speed_layer",
        "clock": clock,
        "zones": rows,
        "grid_total_consumption_kwh": round(total_consumption, 3),
        "grid_total_solar_kwh": round(total_solar, 3),
        "grid_renewable_pct": round(renewable, 2),
        "low_renewable_threshold_pct": LOW_RENEWABLE_PCT_THRESHOLD,
    }


@app.get("/api/grid/history")
def grid_history(minutes: int = Query(default=15, ge=1, le=360)):
    rows = query(
        """
        SELECT grid_zone, window_end, total_consumption_kwh, total_solar_kwh, renewable_pct
        FROM live_zone_metrics
        WHERE window_end <= now() AND window_end > now() - make_interval(mins => %s)
        ORDER BY window_end;
        """,
        (minutes,),
    )
    series = {}
    for r in rows:
        series.setdefault(r["grid_zone"], []).append(r)
    return {"source": "speed_layer", "minutes": minutes, "series": series}


@app.get("/api/households/live")
def households_live(sim_day: int | None = None):
    day = _clock()["sim_day"] if sim_day is None else sim_day
    rows = query(
        """
        SELECT household_id, sim_day, grid_zone, consumption_kwh, solar_kwh, reading_count, last_event_time
        FROM live_household_consumption WHERE sim_day = %s ORDER BY household_id;
        """,
        (day,),
    )
    return {"source": "speed_layer", "sim_day": day, "count": len(rows), "rows": rows}


# ---------------------------------------------------------------------------
# Batch view
# ---------------------------------------------------------------------------
def _latest_billed_day():
    rows = query("SELECT MAX(sim_day) AS d FROM daily_billing_report;")
    return rows[0]["d"] if rows else None


@app.get("/api/billing/daily")
def billing_daily(sim_day: int | None = Query(default=None), household_id: str | None = None):
    """Consolidated daily billing & solar-contribution report (batch layer view)."""
    day = _latest_billed_day() if sim_day is None else sim_day
    if day is None:
        return {"source": "batch_layer", "sim_day": None, "count": 0, "total_billed": 0, "rows": []}
    sql = "SELECT * FROM daily_billing_report WHERE sim_day = %s"
    params = [day]
    if household_id is not None:
        sql += " AND household_id = %s"
        params.append(household_id)
    rows = query(sql + " ORDER BY household_id;", tuple(params))
    total_bill = sum(float(r["bill_amount"]) for r in rows)
    return {"source": "batch_layer", "sim_day": day, "count": len(rows), "total_billed": round(total_bill, 2),
            "rows": rows}


@app.get("/api/billing/summary")
def billing_summary(sim_day: int | None = None):
    """Per-zone billing and solar-contribution roll-up for one billed day."""
    day = _latest_billed_day() if sim_day is None else sim_day
    rows = query(
        """
        SELECT grid_zone, COUNT(*) AS households,
               ROUND(SUM(total_consumption_kwh)::numeric, 2) AS total_consumption_kwh,
               ROUND(SUM(total_solar_kwh)::numeric, 2) AS total_solar_kwh,
               ROUND(SUM(net_consumption_kwh)::numeric, 2) AS net_consumption_kwh,
               ROUND(AVG(solar_contribution_pct)::numeric, 1) AS avg_solar_contribution_pct,
               ROUND(SUM(bill_amount)::numeric, 2) AS total_billed,
               ROUND(AVG(bill_amount)::numeric, 2) AS avg_bill
        FROM daily_billing_report WHERE sim_day = %s
        GROUP BY grid_zone ORDER BY grid_zone;
        """,
        (day,),
    )
    return {"source": "batch_layer", "sim_day": day, "zones": rows}


@app.get("/api/billing/days")
def billing_days():
    rows = query(
        """
        SELECT sim_day, households_billed, total_billed, batch_consumption_kwh, drift_pct, reconciled_at
        FROM batch_reconciliation ORDER BY sim_day DESC LIMIT 60;
        """
    )
    return {"source": "batch_layer", "days": rows}


@app.get("/api/reconciliation")
def reconciliation(limit: int = Query(default=10, ge=1, le=100)):
    rows = query("SELECT * FROM batch_reconciliation ORDER BY sim_day DESC LIMIT %s;", (limit,))
    return {"source": "batch_layer", "rows": rows}


# ---------------------------------------------------------------------------
# Lambda merge: speed view x batch view
# ---------------------------------------------------------------------------
@app.get("/api/billing/projection")
def billing_projection(household_id: str | None = None):
    """Provisional bill for the running sim-day.

    consumption so far  <- speed layer (live_household_consumption, today)
    tariff              <- batch layer (latest validated tariff_reference row)
    formula             <- processing/billing_rules.compute_bill (same as batch)
    The last finalized (batch) bill is returned alongside for comparison.
    """
    clock = _clock()
    sql = """
        SELECT l.household_id, l.grid_zone, l.consumption_kwh, l.solar_kwh, l.reading_count,
               t.tariff_rate, t.billing_tier, t.subsidy_flag, t.sim_day AS tariff_sim_day,
               b.bill_amount AS last_final_bill, b.sim_day AS last_final_sim_day
        FROM live_household_consumption l
        LEFT JOIN LATERAL (SELECT * FROM tariff_reference tr WHERE tr.household_id = l.household_id
                           ORDER BY tr.sim_day DESC LIMIT 1) t ON TRUE
        LEFT JOIN LATERAL (SELECT * FROM daily_billing_report d WHERE d.household_id = l.household_id
                           ORDER BY d.sim_day DESC LIMIT 1) b ON TRUE
        WHERE l.sim_day = %s
    """
    params = [clock["sim_day"]]
    if household_id:
        sql += " AND l.household_id = %s"
        params.append(household_id)
    rows = query(sql + " ORDER BY l.household_id;", tuple(params))
    if household_id and not rows:
        raise HTTPException(status_code=404, detail=f"no live readings for {household_id} today")

    out = []
    for r in rows:
        net = net_consumption_kwh(float(r["consumption_kwh"]), float(r["solar_kwh"]))
        provisional = (compute_bill(net, float(r["tariff_rate"]), bool(r["subsidy_flag"]))
                       if r["tariff_rate"] is not None else None)
        out.append({
            **r,
            "net_consumption_kwh": round(net, 3),
            "solar_contribution_pct": solar_contribution_pct(float(r["consumption_kwh"]), float(r["solar_kwh"])),
            "provisional_bill_so_far": provisional,
            "status": "provisional" if provisional is not None else "awaiting_first_tariff",
        })
    return {
        "source": "lambda_merge(speed_layer consumption x batch_layer tariff)",
        "clock": clock,
        "count": len(out),
        "total_provisional": round(sum(r["provisional_bill_so_far"] or 0 for r in out), 2),
        "rows": out,
    }


# ---------------------------------------------------------------------------
# Observability views
# ---------------------------------------------------------------------------
def _stream_quality():
    r = query(
        """
        SELECT COALESCE(SUM(total_events), 0) AS total_events, COALESCE(SUM(clean_events), 0) AS clean_events,
               COALESCE(SUM(invalid_events), 0) AS invalid_events,
               COALESCE(SUM(duplicate_events), 0) AS duplicate_events,
               AVG(avg_lag_seconds) AS avg_lag_seconds, MAX(max_lag_seconds) AS max_lag_seconds,
               COUNT(*) AS micro_batches
        FROM stream_quality_metrics WHERE recorded_at > now() - interval '5 minutes';
        """
    )[0]
    total = int(r["total_events"])
    r["invalid_rate_pct"] = round(100.0 * int(r["invalid_events"]) / total, 2) if total else 0.0
    r["avg_lag_seconds"] = None if r["avg_lag_seconds"] is None else round(float(r["avg_lag_seconds"]), 2)
    reasons = query(
        """
        SELECT key AS reason, SUM(value::int) AS n
        FROM stream_quality_metrics, jsonb_each_text(invalid_by_reason)
        WHERE recorded_at > now() - interval '5 minutes' GROUP BY key ORDER BY n DESC;
        """
    )
    r["invalid_by_reason"] = {x["reason"]: int(x["n"]) for x in reasons}
    return r


@app.get("/api/pipeline/status")
def pipeline_status():
    return {"clock": _clock(), "components": _components(), "stream_quality_last_5m": _stream_quality()}


@app.get("/api/alerts")
def alerts(resolved: bool = False, limit: int = Query(default=50, ge=1, le=500)):
    rows = query(
        """
        SELECT id, alert_type, scope, severity, message, metric_value, threshold,
               triggered_at, last_seen_at, resolved, resolved_at
        FROM alerts WHERE resolved = %s
        ORDER BY triggered_at DESC LIMIT %s;
        """,
        (resolved, limit),
    )
    return {"count": len(rows), "alerts": rows}


DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True, check_dir=False), name="dashboard")
