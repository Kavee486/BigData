"""Alerting / health-check rule engine.

Runs every CHECK_INTERVAL_SECONDS (or once via --once, as the Airflow DAG
does after each batch run) and evaluates two families of rules:

Business rule
  LOW_RENEWABLE        a zone's latest complete window has renewable_pct below
                       LOW_RENEWABLE_PCT_THRESHOLD during simulated daylight
                       (0% solar at night is expected, not an incident).
Pipeline-health rules
  NO_DATA              a component's heartbeat is older than its own staleness
                       budget (config.COMPONENT_STALE_AFTER_SECONDS).
  COMPONENT_FAILED     a component reported status != OK (e.g. batch job crash).
  HIGH_INVALID_RATE    > INVALID_EVENT_RATE_THRESHOLD_PCT of the events in the
                       last 5 minutes were quarantined by the speed layer.
  HIGH_STREAM_LAG      average event-time -> processing lag of the recent
                       micro-batches exceeds STREAM_LAG_THRESHOLD_SECONDS.
  RECONCILIATION_DRIFT the speed layer's running total for a finished day
                       differs from the batch layer's exact total by more
                       than RECONCILIATION_DRIFT_THRESHOLD_PCT.

Alert lifecycle: at most one OPEN alert per (type, scope) (partial unique
index in init.sql). While the condition holds the open alert's last_seen_at /
metric_value are refreshed; when it clears the alert is auto-resolved. Every
transition is logged as structured JSON and, if ALERT_WEBHOOK_URL is set,
POSTed to that webhook (Slack/Teams-compatible JSON body).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.append("/app")

from config import (
    DAYLIGHT_END_FRACTION,
    DAYLIGHT_START_FRACTION,
    INVALID_EVENT_RATE_THRESHOLD_PCT,
    LOW_RENEWABLE_PCT_THRESHOLD,
    RECONCILIATION_DRIFT_THRESHOLD_PCT,
    STREAM_LAG_THRESHOLD_SECONDS,
    pg_dsn,
    stale_after_seconds,
)
from common.sim_clock import day_fraction_at, is_daylight
from observability.logging_config import get_logger, log_event

logger = get_logger("alerts_engine")

CHECK_INTERVAL_SECONDS = int(os.getenv("ALERT_CHECK_INTERVAL_SECONDS", "15"))
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


# ---------------------------------------------------------------------------
# Pure rule predicates (unit-tested in tests/test_alert_rules.py)
# ---------------------------------------------------------------------------
def low_renewable_breached(renewable_pct, day_fraction: float):
    """True/False when the rule applies, None outside simulated daylight."""
    if not is_daylight(day_fraction, DAYLIGHT_START_FRACTION, DAYLIGHT_END_FRACTION):
        return None
    return renewable_pct is not None and renewable_pct < LOW_RENEWABLE_PCT_THRESHOLD


def is_stale(component: str, age_seconds: float) -> bool:
    return age_seconds > stale_after_seconds(component)


def invalid_rate_pct(invalid_events: int, total_events: int) -> float:
    return 100.0 * invalid_events / total_events if total_events else 0.0


def drift_breached(drift_pct) -> bool:
    return drift_pct is not None and abs(drift_pct) > RECONCILIATION_DRIFT_THRESHOLD_PCT


# ---------------------------------------------------------------------------
# Alert lifecycle helpers
# ---------------------------------------------------------------------------
def _notify(event: str, payload: dict):
    if not ALERT_WEBHOOK_URL:
        return
    try:
        body = json.dumps({"text": f"[{event}] {payload.get('message', '')}", **payload}, default=str).encode()
        req = urllib.request.Request(ALERT_WEBHOOK_URL, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:  # noqa: BLE001 - a broken webhook must not stop alerting
        log_event(logger, "warning", "alert_webhook_failed", error=str(exc))


def raise_alert(cur, alert_type, scope, severity, message, value, threshold):
    cur.execute(
        """
        INSERT INTO alerts (alert_type, scope, severity, message, metric_value, threshold)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (alert_type, scope) WHERE NOT resolved DO UPDATE SET
            last_seen_at = now(), metric_value = EXCLUDED.metric_value, message = EXCLUDED.message
        RETURNING id, (xmax = 0) AS inserted;
        """,
        (alert_type, scope, severity, message, value, threshold),
    )
    alert_id, inserted = cur.fetchone()
    if inserted:
        payload = dict(alert_id=alert_id, type=alert_type, scope=scope, severity=severity,
                       metric_value=value, threshold=threshold, message=message)
        log_event(logger, "error" if severity == "CRITICAL" else "warning", "alert_triggered", **payload)
        _notify("ALERT", payload)


def resolve_alert(cur, alert_type, scope):
    cur.execute(
        """
        UPDATE alerts SET resolved = TRUE, resolved_at = now()
        WHERE alert_type = %s AND scope = %s AND NOT resolved RETURNING id;
        """,
        (alert_type, scope),
    )
    for (alert_id,) in cur.fetchall():
        payload = dict(alert_id=alert_id, type=alert_type, scope=scope, message=f"{alert_type} {scope} resolved")
        log_event(logger, "info", "alert_resolved", **payload)
        _notify("RESOLVED", payload)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def check_low_renewable(cur, epoch):
    cur.execute(
        """
        SELECT DISTINCT ON (grid_zone) grid_zone, renewable_pct, EXTRACT(EPOCH FROM window_end)
        FROM live_zone_metrics WHERE window_end <= now()
        ORDER BY grid_zone, window_start DESC;
        """
    )
    for zone, pct, window_end in cur.fetchall():
        breached = low_renewable_breached(pct, day_fraction_at(float(window_end), epoch))
        if breached:
            raise_alert(cur, "LOW_RENEWABLE", zone, "WARNING",
                        f"Zone {zone} renewable contribution is {pct:.1f}% "
                        f"(below {LOW_RENEWABLE_PCT_THRESHOLD:g}% during daylight)",
                        pct, LOW_RENEWABLE_PCT_THRESHOLD)
        else:
            resolve_alert(cur, "LOW_RENEWABLE", zone)


def check_components(cur):
    cur.execute("SELECT component, status, detail, EXTRACT(EPOCH FROM now() - last_heartbeat) FROM pipeline_health;")
    for component, status, detail, age in cur.fetchall():
        age = float(age)
        if is_stale(component, age):
            raise_alert(cur, "NO_DATA", component, "CRITICAL",
                        f"No heartbeat from {component} for {age / 60:.1f} min "
                        f"(budget {stale_after_seconds(component) / 60:.1f} min)",
                        age, stale_after_seconds(component))
        else:
            resolve_alert(cur, "NO_DATA", component)
        if status != "OK":
            raise_alert(cur, "COMPONENT_FAILED", component, "CRITICAL",
                        f"{component} reported {status}: {detail}", None, None)
        else:
            resolve_alert(cur, "COMPONENT_FAILED", component)


def check_stream_quality(cur):
    cur.execute(
        """
        SELECT COALESCE(SUM(total_events), 0), COALESCE(SUM(invalid_events), 0)
        FROM stream_quality_metrics WHERE recorded_at > now() - interval '5 minutes';
        """
    )
    total, invalid = cur.fetchone()
    rate = invalid_rate_pct(int(invalid), int(total))
    if total and rate > INVALID_EVENT_RATE_THRESHOLD_PCT:
        raise_alert(cur, "HIGH_INVALID_RATE", "speed_layer", "WARNING",
                    f"{rate:.1f}% of events quarantined in the last 5 min "
                    f"(threshold {INVALID_EVENT_RATE_THRESHOLD_PCT:g}%)",
                    rate, INVALID_EVENT_RATE_THRESHOLD_PCT)
    else:
        resolve_alert(cur, "HIGH_INVALID_RATE", "speed_layer")

    cur.execute("SELECT AVG(avg_lag_seconds) FROM (SELECT avg_lag_seconds FROM stream_quality_metrics "
                "ORDER BY recorded_at DESC LIMIT 3) t;")
    (lag,) = cur.fetchone()
    if lag is not None and lag > STREAM_LAG_THRESHOLD_SECONDS:
        raise_alert(cur, "HIGH_STREAM_LAG", "speed_layer", "WARNING",
                    f"Speed layer is {lag:.0f}s behind event time (threshold {STREAM_LAG_THRESHOLD_SECONDS:g}s)",
                    lag, STREAM_LAG_THRESHOLD_SECONDS)
    else:
        resolve_alert(cur, "HIGH_STREAM_LAG", "speed_layer")


def check_reconciliation(cur):
    cur.execute("SELECT sim_day, drift_pct FROM batch_reconciliation ORDER BY sim_day DESC LIMIT 1;")
    row = cur.fetchone()
    if not row:
        return
    sim_day, drift = row
    scope = f"sim_day={sim_day}"
    if drift_breached(drift):
        raise_alert(cur, "RECONCILIATION_DRIFT", scope, "WARNING",
                    f"Speed-layer total for day {sim_day} differs from the exact batch total by {drift:+.1f}%",
                    drift, RECONCILIATION_DRIFT_THRESHOLD_PCT)
    else:
        resolve_alert(cur, "RECONCILIATION_DRIFT", scope)


def run_once():
    import psycopg2
    from common.sim_clock import get_sim_epoch
    from observability.heartbeat import beat

    epoch = get_sim_epoch()
    conn = psycopg2.connect(pg_dsn())
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            check_low_renewable(cur, epoch)
            check_components(cur)
            check_stream_quality(cur)
            check_reconciliation(cur)
            cur.execute("SELECT COUNT(*) FROM alerts WHERE NOT resolved;")
            open_alerts = cur.fetchone()[0]
    finally:
        conn.close()
    beat("alerts_engine", f"open_alerts={open_alerts}", logger=logger)
    return open_alerts


def run_loop():
    log_event(logger, "info", "alerts_engine_started", interval_seconds=CHECK_INTERVAL_SECONDS)
    while True:
        try:
            run_once()
        except Exception as exc:  # noqa: BLE001 - keep the health-check loop alive
            log_event(logger, "error", "alerts_engine_check_failed", error=str(exc))
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single check pass and exit (used by Airflow)")
    args = parser.parse_args()
    if args.once:
        log_event(logger, "info", "alert_check_once", open_alerts=run_once())
    else:
        run_loop()
