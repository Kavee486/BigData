"""Streaming data source: simulated smart meters.

Emits one JSON event per household meter every METER_EMIT_INTERVAL_SECONDS
onto the Kafka topic KAFKA_TOPIC_METER_READINGS. This stands in for the
real-world "continuous streaming source" required by the assignment.

Each event:
    {
      "meter_id": "M-007",
      "household_id": "H-007",
      "power_consumption_kwh": 1.23,
      "solar_generation_kwh": 0.40,
      "grid_zone": "North",
      "timestamp": "2026-08-11T10:15:00.123Z"
    }

Consumption follows a diurnal-ish pattern driven by the simulated clock
(morning/evening peaks) and solar generation follows a daylight bell curve,
so the speed layer has something meaningful to aggregate/alert on.
"""
import json
import math
import random
import sys
import time
from datetime import datetime, timezone

sys.path.append("/app")
from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_METER_READINGS,
    METER_EMIT_INTERVAL_SECONDS,
    NUM_HOUSEHOLDS,
    SIMULATED_DAY_SECONDS,
    GRID_ZONES,
)
from observability.logging_config import get_logger, log_event

logger = get_logger("smart_meter_producer")


def build_producer():
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable

    retries = 0
    while True:
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                linger_ms=50,
                retries=5,
            )
        except NoBrokersAvailable:
            retries += 1
            log_event(logger, "warning", "kafka_not_ready", attempt=retries)
            time.sleep(min(2 * retries, 15))


def simulated_time_of_day_fraction(start_time: float) -> float:
    """Fraction [0,1) of the way through the current simulated day."""
    elapsed = time.time() - start_time
    return (elapsed % SIMULATED_DAY_SECONDS) / SIMULATED_DAY_SECONDS


def simulate_reading(household_idx: int, tod_fraction: float):
    zone = GRID_ZONES[household_idx % len(GRID_ZONES)]

    # Consumption: base load + morning/evening peaks (two bumps over the day)
    base_load = 0.15
    morning_peak = 0.5 * math.exp(-((tod_fraction - 0.30) ** 2) / (2 * 0.02 ** 2 * 25))
    evening_peak = 0.9 * math.exp(-((tod_fraction - 0.75) ** 2) / (2 * 0.03 ** 2 * 25))
    consumption = base_load + morning_peak + evening_peak
    consumption *= random.uniform(0.7, 1.3)
    consumption = max(0.0, round(consumption, 3))

    # Solar: daylight bell curve centered at midday (fraction ~0.5), zero at night
    daylight = math.exp(-((tod_fraction - 0.5) ** 2) / (2 * 0.15 ** 2))
    solar = max(0.0, 0.8 * daylight * random.uniform(0.6, 1.1))
    solar = round(solar, 3)

    # Occasionally simulate a sensor dropout / spike for realism
    if random.random() < 0.01:
        consumption = round(consumption * random.uniform(3, 6), 3)  # spike

    return {
        "meter_id": f"M-{household_idx:03d}",
        "household_id": f"H-{household_idx:03d}",
        "power_consumption_kwh": consumption,
        "solar_generation_kwh": solar,
        "grid_zone": zone,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run():
    producer = build_producer()
    log_event(
        logger, "info", "producer_started",
        topic=KAFKA_TOPIC_METER_READINGS, num_households=NUM_HOUSEHOLDS,
        simulated_day_seconds=SIMULATED_DAY_SECONDS,
    )
    start_time = time.time()
    sent = 0
    errors = 0

    while True:
        tod_fraction = simulated_time_of_day_fraction(start_time)
        for h in range(NUM_HOUSEHOLDS):
            event = simulate_reading(h, tod_fraction)
            try:
                producer.send(
                    KAFKA_TOPIC_METER_READINGS,
                    key=event["household_id"],
                    value=event,
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001 - log and keep the stream alive
                errors += 1
                log_event(logger, "error", "produce_failed", error=str(exc))

        if sent % (NUM_HOUSEHOLDS * 10) == 0:
            producer.flush()
            log_event(logger, "info", "producer_heartbeat", sent_total=sent, errors_total=errors)

        time.sleep(METER_EMIT_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
