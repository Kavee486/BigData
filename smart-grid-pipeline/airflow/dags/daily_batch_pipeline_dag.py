"""Airflow DAG: orchestrates the Lambda batch layer.

For each simulated day:
  1. wait_for_tariff_file - sensor polling BATCH_DROP_DIR for that day's
     tariff CSV + its _SUCCESS marker (the daily-batch source writes the
     marker only after the CSV is fully and atomically written).
  2. run_batch_layer - spark-submit processing/batch_layer_spark.py,
     which recomputes household daily totals from the Parquet lake, loads
     the tariff file, joins them, and writes daily_billing_report.
  3. run_alert_check - re-evaluates alert rules once the batch view lands
     (e.g. a household whose bill is anomalously high).
  4. notify_complete - logs completion (stands in for a Slack/email hook).

Scheduled every SIMULATED_DAY_SECONDS via a time-delta schedule so it lines
up with the compressed simulated clock described in the report.
"""
import glob
import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor
from airflow.operators.bash import BashOperator

sys.path.append("/app")
from config import BATCH_DROP_DIR, SIMULATED_DAY_SECONDS
from observability.logging_config import get_logger, log_event

logger = get_logger("airflow_batch_dag")

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
}


def _current_sim_day(**context):
    """Compute which sim_day this DAG run should process from its logical date."""
    dag_run = context["dag_run"]
    start = context["dag"].start_date or datetime.utcnow()
    elapsed = (dag_run.logical_date - start).total_seconds()
    sim_day = max(0, int(elapsed // SIMULATED_DAY_SECONDS))
    context["ti"].xcom_push(key="sim_day", value=sim_day)
    log_event(logger, "info", "sim_day_resolved", sim_day=sim_day)
    return sim_day


def _find_tariff_file(**context) -> bool:
    ti = context["ti"]
    sim_day = ti.xcom_pull(key="sim_day", task_ids="resolve_sim_day")
    marker = os.path.join(BATCH_DROP_DIR, f"_SUCCESS_simday{sim_day}")
    if not os.path.exists(marker):
        log_event(logger, "info", "waiting_for_tariff_file", sim_day=sim_day)
        return False
    with open(marker) as f:
        filename = f.read().strip()
    filepath = os.path.join(BATCH_DROP_DIR, filename)
    if not os.path.exists(filepath):
        return False
    ti.xcom_push(key="tariff_file", value=filepath)
    log_event(logger, "info", "tariff_file_found", sim_day=sim_day, file=filepath)
    return True


with DAG(
    dag_id="daily_batch_pipeline",
    description="Lambda batch layer: reconcile daily consumption with tariff data and produce the billing report",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule_interval=timedelta(seconds=SIMULATED_DAY_SECONDS),
    catchup=False,
    max_active_runs=1,
    tags=["smart-grid", "batch-layer", "lambda"],
) as dag:

    resolve_sim_day = PythonOperator(
        task_id="resolve_sim_day",
        python_callable=_current_sim_day,
    )

    wait_for_tariff_file = PythonSensor(
        task_id="wait_for_tariff_file",
        python_callable=_find_tariff_file,
        poke_interval=10,
        timeout=SIMULATED_DAY_SECONDS * 2,
        mode="poke",
    )

    run_batch_layer = BashOperator(
        task_id="run_batch_layer",
        bash_command=(
            "spark-submit --master local[2] "
            "--packages org.postgresql:postgresql:42.7.3 "
            "/app/processing/batch_layer_spark.py "
            "--sim-day {{ ti.xcom_pull(key='sim_day', task_ids='resolve_sim_day') }} "
            "--tariff-file '{{ ti.xcom_pull(key='tariff_file', task_ids='wait_for_tariff_file') }}'"
        ),
    )

    run_alert_check = BashOperator(
        task_id="run_alert_check",
        bash_command="python /app/observability/alerts.py --once",
    )

    def _notify_complete(**context):
        sim_day = context["ti"].xcom_pull(key="sim_day", task_ids="resolve_sim_day")
        log_event(logger, "info", "daily_batch_pipeline_complete", sim_day=sim_day)

    notify_complete = PythonOperator(
        task_id="notify_complete",
        python_callable=_notify_complete,
    )

    resolve_sim_day >> wait_for_tariff_file >> run_batch_layer >> run_alert_check >> notify_complete
