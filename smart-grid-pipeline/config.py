"""Central configuration for the Smart Grid Lambda pipeline.

Every component (producers, Spark jobs, API, Airflow DAG) reads config from
here so the whole system can be reconfigured from one place / env vars.
"""
import os

# ---- Simulated clock -------------------------------------------------
# 1 simulated "day" = SIMULATED_DAY_SECONDS of real time.
# Default: 5 minutes = 300s, per the assignment's suggested compression.
SIMULATED_DAY_SECONDS = int(os.getenv("SIMULATED_DAY_SECONDS", "300"))
METER_EMIT_INTERVAL_SECONDS = float(os.getenv("METER_EMIT_INTERVAL_SECONDS", "2"))

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
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )

# ---- Data lake (batch layer raw storage) ---------------------------------
DATA_LAKE_ROOT = os.getenv("DATA_LAKE_ROOT", "/data/lake")
RAW_EVENTS_PATH = os.path.join(DATA_LAKE_ROOT, "raw_meter_events")
BATCH_DROP_DIR = os.getenv("BATCH_DROP_DIR", "/data/batch_drop")

# ---- Domain -----------------------------------------------------------
GRID_ZONES = ["North", "South", "East", "West"]
NUM_HOUSEHOLDS = int(os.getenv("NUM_HOUSEHOLDS", "24"))
NUM_METERS = NUM_HOUSEHOLDS  # 1 meter per household for this simulation

# ---- Alerting thresholds --------------------------------------------------
LOW_RENEWABLE_PCT_THRESHOLD = float(os.getenv("LOW_RENEWABLE_PCT_THRESHOLD", "10.0"))  # percent
NO_DATA_ALERT_MINUTES = float(os.getenv("NO_DATA_ALERT_MINUTES", "2.0"))

# ---- Speed layer windowing ------------------------------------------------
SPEED_LAYER_WINDOW = os.getenv("SPEED_LAYER_WINDOW", "30 seconds")
SPEED_LAYER_SLIDE = os.getenv("SPEED_LAYER_SLIDE", "15 seconds")
SPEED_LAYER_WATERMARK = os.getenv("SPEED_LAYER_WATERMARK", "1 minutes")

# ---- API -----------------------------------------------------------------
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
