"""Data-quality rules for smart-meter events -- single source of truth.

The speed layer (Spark) builds its validation expression from the same
constants and in the same order (see speed_layer_spark.invalid_reason_col),
and validate_event() below is the plain-Python reference implementation that
the unit tests exercise. An event failing any rule is quarantined (written to
the quarantine Parquet path with its reason) instead of being aggregated.
"""
from datetime import datetime

from config import GRID_ZONES

# A household meter cannot plausibly report more than this per 2s reading;
# anything above is a sensor fault, not a real (even spiky) load.
MAX_READING_KWH = 50.0

REQUIRED_FIELDS = ("event_id", "meter_id", "household_id", "grid_zone", "timestamp")

# Reason codes, in evaluation order (first failing rule wins).
MISSING_FIELD = "missing_field"
BAD_TIMESTAMP = "bad_timestamp"
UNKNOWN_ZONE = "unknown_zone"
NEGATIVE_VALUE = "negative_value"
OUT_OF_RANGE = "out_of_range"


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_event(event: dict):
    """Return None if the event is clean, else the reason code it fails."""
    for field in REQUIRED_FIELDS:
        if event.get(field) in (None, ""):
            return MISSING_FIELD
    if event.get("power_consumption_kwh") is None or event.get("solar_generation_kwh") is None:
        return MISSING_FIELD
    if _parse_ts(event["timestamp"]) is None:
        return BAD_TIMESTAMP
    if event["grid_zone"] not in GRID_ZONES:
        return UNKNOWN_ZONE
    consumption = float(event["power_consumption_kwh"])
    solar = float(event["solar_generation_kwh"])
    if consumption < 0 or solar < 0:
        return NEGATIVE_VALUE
    if consumption > MAX_READING_KWH or solar > MAX_READING_KWH:
        return OUT_OF_RANGE
    return None
