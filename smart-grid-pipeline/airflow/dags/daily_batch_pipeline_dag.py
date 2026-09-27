"""Airflow DAG: orchestrates the Lambda batch layer.

Runs every BATCH_DAG_SCHEDULE_SECONDS (default 60s) and, for the OLDEST
finished simulated day that has not been billed yet:

  1. resolve_sim_day      ShortCircuit: pick the target day from the shared
                          sim clock + Postgres; skip the rest of the run when
                          there is nothing to do (the normal case between day
                          boundaries). Doubles as automatic backfill after
                          downtime (up to LOOKBACK_DAYS).
  2. wait_for_tariff_file sensor on the _SUCCESS marker of that day's tariff
                          extract (written only after the CSV is atomically
                          in place).
  3. run_batch_layer      spark-submit processing/batch_layer_spark.py: exact
                          recompute from the Parquet lake, tariff validation +
                          fallback, join, bill, speed/batch reconciliation.
  4. publish_report       write the consolidated CSV + HTML report files.
  5. run_alert_check      re-evaluate every alert rule (incl. reconciliation
                          drift) right after the batch view lands.
  6. notify_complete      structured completion log (stand-in for Slack/email).

Why a frequent poll instead of a once-per-day cron: with the compressed clock a
day ends every 5 minutes at an arbitrary wall-clock offset; polling +
ShortCircuit bills each day within about a minute of its tariff file arriving
and never double-processes a day. Retries + on_failure_callback give failure
visibility (structured log line + CRITICAL alert in the alerts table).
"""
import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.sensors.python import PythonSensor

sys.path.append("/app")
from config import BATCH_DAG_SCHEDULE_SECONDS, BATCH_DROP_DIR, RAW_EVENTS_PATH, SIMULATED_DAY_SECONDS, pg_dsn
from observability.logging_config import get_logger, log_event

logger = get_logger("airflow_batch_dag")
LOOKBACK_DAYS = 3


def _on_failure(context):
    ti = context["task_instance"]
    sim_day = ti.xcom_pull(key="sim_day", task_ids="resolve_sim_day")
    log_event(logger, "error", "dag_task_failed", dag_id=ti.dag_id, task_id=ti.task_id, try_number=ti.try_number,
              sim_day=sim_day, error=str(context.get("exception")))
    try:
        import psycopg2
        from observability.alerts import raise_alert

        conn = psycopg2.connect(pg_dsn())
        conn.autocommit = True
        with conn.cursor() as cur:
            raise_alert(cur, "PIPELINE_TASK_FAILED", f"{ti.dag_id}.{ti.task_id}", "CRITICAL",
                        f"Airflow task {ti.task_id} failed for sim_day={sim_day}: {context.get('exception')}",
                        None, None)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "error", "failure_alert_not_recorded", error=str(exc))


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(seconds=20),
    "on_failure_callback": _on_failure,
}


def _resolve_sim_day(**context) -> bool:
    import psycopg2
    from common.sim_clock import current_sim_day, get_sim_epoch

    current = current_sim_day(get_sim_epoch())
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT sim_day FROM daily_billing_report WHERE sim_day >= %s;",
                        (current - LOOKBACK_DAYS,))
            billed = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    pending = [d for d in range(max(0, current - LOOKBACK_DAYS), current) if d not in billed]
    # A day with no raw partition at all (pipeline down the whole day) cannot
    # be billed; skip it rather than blocking every later day.
    pending = [d for d in pending if os.path.isdir(os.path.join(RAW_EVENTS_PATH, f"sim_day={d}"))]
    if not pending:
        log_event(logger, "info", "nothing_to_bill", current_sim_day=current)
        return False
    target = pending[0]
    context["ti"].xcom_push(key="sim_day", value=target)
    log_event(logger, "info", "sim_day_resolved", sim_day=target, current_sim_day=current, pending=pending)
    return True


def _find_tariff_file(**context) -> bool:
    ti = context["ti"]
    sim_day = ti.xcom_pull(key="sim_day", task_ids="resolve_sim_day")
    marker = os.path.join(BATCH_DROP_DIR, f"_SUCCESS_simday{sim_day}")
    if not os.path.exists(marker):
        log_event(logger, "info", "waiting_for_tariff_file", sim_day=sim_day)
        return False
    with open(marker) as f:
        filepath = os.path.join(BATCH_DROP_DIR, f.read().strip())
    if not os.path.exists(filepath):
        return False
    ti.xcom_push(key="tariff_file", value=filepath)
    log_event(logger, "info", "tariff_file_found", sim_day=sim_day, file=filepath)
    return True


def _publish_report(**context):
    from serving.report_generator import write_report

    sim_day = context["ti"].xcom_pull(key="sim_day", task_ids="resolve_sim_day")
    result = write_report(sim_day)
    log_event(logger, "info", "report_published", sim_day=sim_day, **result)
    return result


def _notify_complete(**context):
    ti = context["ti"]
    sim_day = ti.xcom_pull(key="sim_day", task_ids="resolve_sim_day")
    report = ti.xcom_pull(task_ids="publish_report") or {}
    log_event(logger, "info", "daily_batch_pipeline_complete", sim_day=sim_day,
              total_billed=report.get("total_billed"), report_html=report.get("html"))


with DAG(
    dag_id="daily_batch_pipeline",
    description="Lambda batch layer: exact daily recompute, tariff join, billing report, reconciliation",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=timedelta(seconds=BATCH_DAG_SCHEDULE_SECONDS),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    dagrun_timeout=timedelta(seconds=SIMULATED_DAY_SECONDS * 3),
    tags=["smart-grid", "batch-layer", "lambda"],
) as dag:

    resolve_sim_day = ShortCircuitOperator(task_id="resolve_sim_day", python_callable=_resolve_sim_day)

    wait_for_tariff_file = PythonSensor(
        task_id="wait_for_tariff_file",
        python_callable=_find_tariff_file,
        poke_interval=10,
        timeout=SIMULATED_DAY_SECONDS,
        mode="poke",
    )

    run_batch_layer = BashOperator(
        task_id="run_batch_layer",
        bash_command=(
            "spark-submit --master 'local[2]' --driver-memory 1g "
            "/app/processing/batch_layer_spark.py "
            "--sim-day {{ ti.xcom_pull(key='sim_day', task_ids='resolve_sim_day') }} "
            "--tariff-file '{{ ti.xcom_pull(key='tariff_file', task_ids='wait_for_tariff_file') }}'"
        ),
        execution_timeout=timedelta(seconds=SIMULATED_DAY_SECONDS * 2),
    )

    publish_report = PythonOperator(task_id="publish_report", python_callable=_publish_report)

    run_alert_check = BashOperator(task_id="run_alert_check", bash_command="python /app/observability/alerts.py --once")

    notify_complete = PythonOperator(task_id="notify_complete", python_callable=_notify_complete)

    resolve_sim_day >> wait_for_tariff_file >> run_batch_layer >> publish_report >> run_alert_check >> notify_complete
