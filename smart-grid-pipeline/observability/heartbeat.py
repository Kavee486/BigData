"""Best-effort component heartbeats into Postgres `pipeline_health`.

Every long-running component calls beat() periodically. The /health endpoint,
the Prometheus staleness gauge and the NO_DATA alert rule all read this table,
so a silent component is detected no matter which stage failed. A heartbeat
failure is logged but never allowed to crash the component itself.
"""
import psycopg2

from config import pg_dsn


def beat(component: str, detail: str = "", status: str = "OK", logger=None) -> None:
    try:
        conn = psycopg2.connect(pg_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_health (component, last_heartbeat, status, detail)
                    VALUES (%s, now(), %s, %s)
                    ON CONFLICT (component) DO UPDATE SET
                        last_heartbeat = now(), status = EXCLUDED.status, detail = EXCLUDED.detail;
                    """,
                    (component, status, detail),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        if logger is not None:
            from observability.logging_config import log_event
            log_event(logger, "warning", "heartbeat_failed", component=component, error=str(exc))
