"""Central configuration for the Smart Grid Lambda pipeline.

Every component (producers, Spark jobs, API, Airflow DAG, alert engine) reads
config from here so the whole system can be reconfigured from one place via
environment variables (see docker-compose.yml / .env.example).
"""
import os

# ---- Simulated clock -------------------------------------------------
# 1 simulated "day" = SIMULATED_DAY_SECONDS of real time.
# Default: 5 minutes = 300s, per the assignment's suggested compression.
# Day numbering is anchored to a single shared epoch stored in Postgres
# (table sim_clock, see common/sim_clock.py) so every container agrees on
# which sim_day an event belongs to.
SIMULATED_DAY_SECONDS = int(os.getenv("SIMULATED_DAY_SECONDS", "300"))
METER_EMIT_INTERVAL_SECONDS = float(os.getenv("METER_EMIT_INTERVAL_SECONDS", "2"))
# Grace period after a sim-day ends before the end-of-day tariff extract is
# dropped: lets the speed layer flush the day's last micro-batches to the lake.
TARIFF_DROP_GRACE_SECONDS = int(os.getenv("TARIFF_DROP_GRACE_SECONDS", "20"))

# ---- Kafka -------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_METER_READINGS = os.getenv("KAFKA_TOPIC_METER_READINGS", "smart-meter-readings")
KAFKA_PARTITIONS = int(os.getenv("KAFKA_PARTITIONS", "3"))
KAFKA_REPLICATION_FACTOR = int(os.getenv("KAFKA_REPLICATION_FACTOR", "1"))

# ---- Postgres ------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "smartgrid")
POSTGRES_USER = os.getenv("POSTGRES_USER", "smartgrid")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "smartgrid")

POSTGRES_JDBC_URL = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


def pg_dsn() -> str:
    return (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD} connect_timeout=5"
    )


# ---- Data lake (batch layer raw storage) ---------------------------------
DATA_LAKE_ROOT = os.getenv("DATA_LAKE_ROOT", "/data/lake")
RAW_EVENTS_PATH = os.path.join(DATA_LAKE_ROOT, "raw_meter_events")
QUARANTINE_PATH = os.path.join(DATA_LAKE_ROOT, "quarantine_meter_events")
CHECKPOINT_ROOT = os.path.join(DATA_LAKE_ROOT, "_checkpoints")
BATCH_DROP_DIR = os.getenv("BATCH_DROP_DIR", "/data/batch_drop")
REPORTS_DIR = os.getenv("REPORTS_DIR", "/data/reports")

# ---- Domain -----------------------------------------------------------
GRID_ZONES = ["North", "South", "East", "West"]
NUM_HOUSEHOLDS = int(os.getenv("NUM_HOUSEHOLDS", "24"))
NUM_METERS = NUM_HOUSEHOLDS  # 1 meter per household for this simulation

# Share of emitted events that are deliberately "dirty" (malformed / invalid
# values / duplicates) so the processing layer's cleaning logic is exercised.
DIRTY_EVENT_RATE = float(os.getenv("DIRTY_EVENT_RATE", "0.01"))

# ---- Alerting thresholds --------------------------------------------------
LOW_RENEWABLE_PCT_THRESHOLD = float(os.getenv("LOW_RENEWABLE_PCT_THRESHOLD", "10.0"))  # percent
# Renewable contribution is only judged during simulated daylight (as a
# fraction of the sim day); at night 0% solar is expected, not an incident.
DAYLIGHT_START_FRACTION = float(os.getenv("DAYLIGHT_START_FRACTION", "0.40"))
DAYLIGHT_END_FRACTION = float(os.getenv("DAYLIGHT_END_FRACTION", "0.60"))
NO_DATA_ALERT_MINUTES = float(os.getenv("NO_DATA_ALERT_MINUTES", "2.0"))
INVALID_EVENT_RATE_THRESHOLD_PCT = float(os.getenv("INVALID_EVENT_RATE_THRESHOLD_PCT", "5.0"))
STREAM_LAG_THRESHOLD_SECONDS = float(os.getenv("STREAM_LAG_THRESHOLD_SECONDS", "60"))
RECONCILIATION_DRIFT_THRESHOLD_PCT = float(os.getenv("RECONCILIATION_DRIFT_THRESHOLD_PCT", "10.0"))

# How long each component may stay silent before it is considered stale.
# Components heartbeat at very different cadences (the batch layer only runs
# once per simulated day), so one global threshold would cause false alerts.
_NO_DATA_SECONDS = NO_DATA_ALERT_MINUTES * 60
COMPONENT_STALE_AFTER_SECONDS = {
    "meter_producer": _NO_DATA_SECONDS,
    "speed_layer": _NO_DATA_SECONDS,
    "alerts_engine": _NO_DATA_SECONDS,
    "batch_layer": 2 * SIMULATED_DAY_SECONDS + _NO_DATA_SECONDS,
}


def stale_after_seconds(component: str) -> float:
    return COMPONENT_STALE_AFTER_SECONDS.get(component, _NO_DATA_SECONDS)


# ---- Speed layer windowing ------------------------------------------------
SPEED_LAYER_WINDOW = os.getenv("SPEED_LAYER_WINDOW", "30 seconds")
SPEED_LAYER_SLIDE = os.getenv("SPEED_LAYER_SLIDE", "15 seconds")
SPEED_LAYER_WATERMARK = os.getenv("SPEED_LAYER_WATERMARK", "1 minutes")
SPEED_LAYER_TRIGGER = os.getenv("SPEED_LAYER_TRIGGER", "10 seconds")

# ---- Batch orchestration ---------------------------------------------------
# The DAG polls this often for a completed sim-day that has not been billed
# yet (ShortCircuit skips the run when there is nothing to do).
BATCH_DAG_SCHEDULE_SECONDS = int(os.getenv("BATCH_DAG_SCHEDULE_SECONDS", "60"))

# ---- API / metrics -----------------------------------------------------------
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
PRODUCER_METRICS_PORT = int(os.getenv("PRODUCER_METRICS_PORT", "8001"))
