"""Shared simulated clock.

All components must agree on which simulated day a reading belongs to, or the
batch layer would join the wrong day's consumption with the wrong tariff file.
We therefore anchor day numbering to ONE epoch that Postgres records when the
database is first initialised (storage/init.sql -> table sim_clock), instead
of each process counting from its own start time.

    sim_day(t)       = floor((t - epoch) / SIMULATED_DAY_SECONDS)
    day_fraction(t)  = ((t - epoch) mod SIMULATED_DAY_SECONDS) / SIMULATED_DAY_SECONDS

day_fraction 0.0 is simulated midnight, 0.5 is simulated noon.
SIM_EPOCH (unix seconds) can be set explicitly, e.g. in tests or when running
a component outside Docker without Postgres.
"""
import os
import time

from config import SIMULATED_DAY_SECONDS, pg_dsn

_cached_epoch = None


def get_sim_epoch(max_wait_seconds: float = 120.0) -> float:
    """Return the shared epoch (unix seconds), waiting for Postgres if needed."""
    global _cached_epoch
    if _cached_epoch is not None:
        return _cached_epoch
    if os.getenv("SIM_EPOCH"):
        _cached_epoch = float(os.environ["SIM_EPOCH"])
        return _cached_epoch

    import psycopg2  # local import: pure helpers below are usable without it

    deadline = time.time() + max_wait_seconds
    while True:
        try:
            conn = psycopg2.connect(pg_dsn())
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT EXTRACT(EPOCH FROM epoch) FROM sim_clock WHERE id = 1;")
                    _cached_epoch = float(cur.fetchone()[0])
                    return _cached_epoch
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - Postgres may still be starting
            if time.time() > deadline:
                raise
            time.sleep(3)


def sim_day_at(ts: float, epoch: float) -> int:
    return int((ts - epoch) // SIMULATED_DAY_SECONDS)


def day_fraction_at(ts: float, epoch: float) -> float:
    return ((ts - epoch) % SIMULATED_DAY_SECONDS) / SIMULATED_DAY_SECONDS


def day_start(sim_day: int, epoch: float) -> float:
    return epoch + sim_day * SIMULATED_DAY_SECONDS


def day_end(sim_day: int, epoch: float) -> float:
    return epoch + (sim_day + 1) * SIMULATED_DAY_SECONDS


def current_sim_day(epoch: float | None = None) -> int:
    return sim_day_at(time.time(), get_sim_epoch() if epoch is None else epoch)


def is_daylight(fraction: float, start: float, end: float) -> bool:
    return start <= fraction <= end
