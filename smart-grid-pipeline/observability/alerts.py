"""Alerting / health-check engine.

Two rule types, run on a loop (or once via --once, e.g. from the Airflow DAG):

  1. LOW_RENEWABLE  - a zone's latest window has renewable_pct below
     LOW_RENEWABLE_PCT_THRESHOLD -> business-relevant "the grid is drawing
     too much from non-renewable sources right now" alert.
  2. NO_DATA        - a pipeline component's last_heartbeat in
     pipeline_health is older than NO_DATA_ALERT_MINUTES -> operational
     "the pipeline itself may be broken/stalled" alert.

Alerts are inserted into the `alerts` table (deduplicated: we skip firing
the same alert scope+type again within a short cooldown) and are exposed
via the API's /api/alerts endpoint.
"""
import argparse
import sys
import time

sys.path.append("/app")
import psycopg2
import psycopg2.extras

from config import pg_dsn, LOW_RENEWABLE_PCT_THRESHOLD, NO_DATA_ALERT_MINUTES
from observability.logging_config import get_logger, log_event

logger = get_logger("alerts_engine")

CHECK_INTERVAL_SECONDS = 15
COOLDOWN_SECONDS = 60


def get_conn():
    return psycopg2.connect(pg_dsn())


def _recently_alerted(cur, alert_type: str, scope: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM alerts
        WHERE alert_type = %s AND scope = %s
          AND triggered_at > now() - (%s || ' seconds')::interval
        LIMIT 1;
        """,
        (alert_type, scope, COOLDOWN_SECONDS),
    )
    return cur.fetchone() is not None


def check_low_renewable(cur):
    cur.execute(
        """
        SELECT DISTINCT ON (grid_zone) grid_zone, renewable_pct, window_start
        FROM live_zone_metrics
        ORDER BY grid_zone, window_start DESC;
        """
    )
    for row in cur.fetchall():
        zone, pct, window_start = row
        if pct is None or pct >= LOW_RENEWABLE_PCT_THRESHOLD:
            continue
        if _recently_alerted(cur, "LOW_RENEWABLE", zone):
            continue
        cur.execute(
            """
            INSERT INTO alerts (alert_type, scope, severity, message, metric_value, threshold)
            VALUES ('LOW_RENEWABLE', %s, 'WARNING', %s, %s, %s);
            """,
            (
                zone,
                f"Zone {zone} renewable contribution is {pct:.1f}% (below {LOW_RENEWABLE_PCT_THRESHOLD}% threshold)",
                pct, LOW_RENEWABLE_PCT_THRESHOLD,
            ),
        )
        log_event(logger, "warning", "alert_triggered", type="LOW_RENEWABLE", zone=zone, renewable_pct=pct)


def check_no_data(cur):
    cur.execute("SELECT component, last_heartbeat FROM pipeline_health;")
    for component, last_heartbeat in cur.fetchall():
        cur.execute("SELECT now() - %s;", (last_heartbeat,))
        age = cur.fetchone()[0]
        age_minutes = age.total_seconds() / 60.0
        if age_minutes < NO_DATA_ALERT_MINUTES:
            continue
        if _recently_alerted(cur, "NO_DATA", component):
            continue
        cur.execute(
            """
            INSERT INTO alerts (alert_type, scope, severity, message, metric_value, threshold)
            VALUES ('NO_DATA', %s, 'CRITICAL', %s, %s, %s);
            """,
            (
                component,
                f"No heartbeat from {component} in {age_minutes:.1f} minutes (threshold {NO_DATA_ALERT_MINUTES})",
                age_minutes, NO_DATA_ALERT_MINUTES,
            ),
        )
        log_event(logger, "error", "alert_triggered", type="NO_DATA", component=component, age_minutes=age_minutes)


def run_once():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        check_low_renewable(cur)
        check_no_data(cur)
    finally:
        cur.close()
        conn.close()


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
        run_once()
    else:
        run_loop()
