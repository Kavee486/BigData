"""Daily-batch data source: tariff / billing reference feed.

Once per simulated day, drops a CSV file into BATCH_DROP_DIR containing
per-household tariff/billing reference data, as if produced by an external
billing system's end-of-day extract:

    household_id,tariff_rate,billing_tier,subsidy_flag,day

The Airflow-orchestrated batch layer picks this file up, joins it against
that day's raw consumption events, and produces the daily billing report.

File name encodes the simulated day so the batch DAG can find "today's"
file deterministically: tariff_YYYY-MM-DD_simday<N>.csv
"""
import csv
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.append("/app")
from config import BATCH_DROP_DIR, NUM_HOUSEHOLDS, SIMULATED_DAY_SECONDS
from observability.logging_config import get_logger, log_event

logger = get_logger("tariff_batch_source")

TIERS = ["residential_low", "residential_standard", "residential_high"]


def generate_tariff_row(household_idx: int, sim_day: int):
    tier = random.choices(TIERS, weights=[0.3, 0.5, 0.2])[0]
    base_rate = {"residential_low": 18.0, "residential_standard": 25.0, "residential_high": 32.0}[tier]
    tariff_rate = round(base_rate * random.uniform(0.95, 1.08), 2)  # LKR per kWh, small daily drift
    subsidy_flag = random.random() < 0.15
    return {
        "household_id": f"H-{household_idx:03d}",
        "tariff_rate": tariff_rate,
        "billing_tier": tier,
        "subsidy_flag": subsidy_flag,
        "day": sim_day,
    }


def write_daily_file(sim_day: int):
    os.makedirs(BATCH_DROP_DIR, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"tariff_{date_str}_simday{sim_day}.csv"
    path = os.path.join(BATCH_DROP_DIR, filename)
    tmp_path = path + ".tmp"

    rows = [generate_tariff_row(h, sim_day) for h in range(NUM_HOUSEHOLDS)]
    with open(tmp_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["household_id", "tariff_rate", "billing_tier", "subsidy_flag", "day"])
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, path)  # atomic drop: consumers never see a partial file

    marker_path = os.path.join(BATCH_DROP_DIR, "_SUCCESS_simday" + str(sim_day))
    with open(marker_path, "w") as f:
        f.write(filename)

    log_event(logger, "info", "batch_file_dropped", file=filename, rows=len(rows), sim_day=sim_day)
    return path


def run():
    log_event(logger, "info", "batch_source_started", simulated_day_seconds=SIMULATED_DAY_SECONDS)
    sim_day = 0
    while True:
        write_daily_file(sim_day)
        sim_day += 1
        time.sleep(SIMULATED_DAY_SECONDS)


if __name__ == "__main__":
    run()
