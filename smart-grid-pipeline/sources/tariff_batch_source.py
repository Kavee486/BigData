"""Daily-batch data source: end-of-day tariff / billing reference extract.

Once per simulated day -- shortly after the day ends (TARIFF_DROP_GRACE_SECONDS)
-- the utility's billing system "publishes" that day's per-household tariff
file into BATCH_DROP_DIR, exactly like an external end-of-day extract:

    household_id,tariff_rate,billing_tier,subsidy_flag,sim_day,published_at

    tariff_simday<N>.csv   + marker   _SUCCESS_simday<N>

Robustness properties:
  * atomic drop -- written to *.tmp then os.replace()d, and the _SUCCESS
    marker is written last, so a consumer never reads a half-written file;
  * deterministic -- tier/subsidy are fixed per household and the daily rate
    drift is seeded by (household, day), so regenerating a day's file yields
    the identical file (safe replays / backfills);
  * catch-up on restart -- any completed day without a marker is dropped on
    start-up, so a crashed source does not leave permanent gaps;
  * realistic imperfections -- roughly one file in three contains an invalid
    row (blank or non-positive tariff_rate) and some contain a duplicated
    household row. The batch layer must reject/deduplicate these and fall
    back to the household's last known valid tariff.
"""
import csv
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.append("/app")
from config import BATCH_DROP_DIR, NUM_HOUSEHOLDS, SIMULATED_DAY_SECONDS, TARIFF_DROP_GRACE_SECONDS
from common.sim_clock import day_end
from observability.logging_config import get_logger, log_event

logger = get_logger("tariff_batch_source")

TIERS = ["residential_low", "residential_standard", "residential_high"]
BASE_RATE_LKR = {"residential_low": 18.0, "residential_standard": 25.0, "residential_high": 32.0}
FIELDNAMES = ["household_id", "tariff_rate", "billing_tier", "subsidy_flag", "sim_day", "published_at"]
MAX_CATCHUP_DAYS = 7


def household_profile(household_idx: int) -> tuple:
    """Tier and subsidy eligibility are properties of the household, not the day."""
    rng = random.Random(f"household-{household_idx}")
    tier = rng.choices(TIERS, weights=[0.3, 0.5, 0.2])[0]
    return tier, rng.random() < 0.15


def generate_tariff_row(household_idx: int, sim_day: int) -> dict:
    tier, subsidy = household_profile(household_idx)
    rng = random.Random(f"tariff-{household_idx}-{sim_day}")
    return {
        "household_id": f"H-{household_idx:03d}",
        "tariff_rate": round(BASE_RATE_LKR[tier] * rng.uniform(0.95, 1.08), 2),  # LKR/kWh, daily drift
        "billing_tier": tier,
        "subsidy_flag": subsidy,
        "sim_day": sim_day,
    }


def generate_daily_rows(sim_day: int, num_households: int = NUM_HOUSEHOLDS) -> list:
    rows = [generate_tariff_row(h, sim_day) for h in range(num_households)]
    rng = random.Random(f"defects-{sim_day}")
    if rng.random() < 0.35:  # an invalid rate from the upstream system
        victim = rng.randrange(num_households)
        rows[victim] = dict(rows[victim], tariff_rate=rng.choice(["", "-1", "0"]))
    if rng.random() < 0.25:  # a household exported twice
        rows.append(dict(rows[rng.randrange(num_households)]))
    return rows


def marker_path(sim_day: int) -> str:
    return os.path.join(BATCH_DROP_DIR, f"_SUCCESS_simday{sim_day}")


def write_daily_file(sim_day: int) -> str:
    os.makedirs(BATCH_DROP_DIR, exist_ok=True)
    filename = f"tariff_simday{sim_day}.csv"
    path = os.path.join(BATCH_DROP_DIR, filename)
    tmp_path = path + ".tmp"

    published_at = datetime.now(timezone.utc).isoformat()
    rows = [dict(r, published_at=published_at) for r in generate_daily_rows(sim_day)]
    with open(tmp_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, path)  # atomic drop: consumers never see a partial file

    with open(marker_path(sim_day), "w") as f:  # marker last => file is complete
        f.write(filename)

    log_event(logger, "info", "batch_file_dropped", file=filename, rows=len(rows), sim_day=sim_day)
    return path


def run():
    from common.sim_clock import current_sim_day, get_sim_epoch
    from observability.heartbeat import beat

    epoch = get_sim_epoch()
    log_event(logger, "info", "batch_source_started", simulated_day_seconds=SIMULATED_DAY_SECONDS,
              grace_seconds=TARIFF_DROP_GRACE_SECONDS)
    next_day = max(0, current_sim_day(epoch) - MAX_CATCHUP_DAYS)
    last_beat = 0.0
    while True:
        # Drop every completed day (plus grace) that has no marker yet.
        while time.time() >= day_end(next_day, epoch) + TARIFF_DROP_GRACE_SECONDS:
            if not os.path.exists(marker_path(next_day)):
                try:
                    write_daily_file(next_day)
                    beat("tariff_batch_source", f"dropped sim_day={next_day}", logger=logger)
                except OSError as exc:
                    log_event(logger, "error", "batch_file_drop_failed", sim_day=next_day, error=str(exc))
                    break  # retry the same day on the next loop
            next_day += 1
        if time.time() - last_beat > 30:
            beat("tariff_batch_source", f"waiting for end of sim_day={next_day}", logger=logger)
            last_beat = time.time()
        time.sleep(5)


if __name__ == "__main__":
    run()
