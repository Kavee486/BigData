"""Streaming data source: simulated smart meters -> Kafka.

Emits one JSON event per household meter every METER_EMIT_INTERVAL_SECONDS
onto the Kafka topic KAFKA_TOPIC_METER_READINGS (created explicitly with
KAFKA_PARTITIONS partitions). Events are keyed by household_id, so all of a
household's readings land on the same partition and stay in order, while the
24 households spread across partitions for parallel consumption.

Each event:
    {
      "event_id": "5f1c...",            # uuid4 -> dedup + tracing key
      "meter_id": "M-007",
      "household_id": "H-007",
      "power_consumption_kwh": 1.23,
      "solar_generation_kwh": 0.40,
      "grid_zone": "North",
      "timestamp": "2026-08-11T10:15:00.123456+00:00"
    }

Realism built into the simulation (all driven by the shared simulated clock):
  * consumption: base load + morning and evening peaks, +/-30% noise, and ~1%
    legitimate demand spikes (x3-x6);
  * solar: daylight bell curve centred on simulated noon, scaled by a per-zone
    installed capacity (South has few panels) and a per-day cloud factor;
    each simulated day one zone gets a heavy overcast spell, which is what
    drives the LOW_RENEWABLE business alert;
  * DIRTY_EVENT_RATE (default 1%) of events are deliberately bad -- missing
    fields, negative or impossible values, unparsable timestamps, or exact
    duplicates (at-least-once redelivery) -- so the processing layer's
    cleaning / quarantine / dedup logic is exercised continuously.
"""
import json
import math
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.append("/app")
from config import (
    DIRTY_EVENT_RATE,
    GRID_ZONES,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PARTITIONS,
    KAFKA_REPLICATION_FACTOR,
    KAFKA_TOPIC_METER_READINGS,
    METER_EMIT_INTERVAL_SECONDS,
    NUM_HOUSEHOLDS,
    PRODUCER_METRICS_PORT,
    SIMULATED_DAY_SECONDS,
)
from common.sim_clock import day_fraction_at, sim_day_at
from observability.logging_config import get_logger, log_event

logger = get_logger("meter_producer")

# Installed solar capacity relative to an average zone.
ZONE_SOLAR_CAPACITY = {"North": 1.2, "South": 0.45, "East": 1.0, "West": 0.9}
OVERCAST_SPELL_LENGTH = 0.12  # fraction of a sim day
DIRTY_KINDS = ("missing_field", "negative_value", "bad_timestamp", "out_of_range", "duplicate")


# ---------------------------------------------------------------------------
# Pure simulation functions (unit-tested, no Kafka needed)
# ---------------------------------------------------------------------------
def daily_weather(sim_day: int) -> dict:
    """Deterministic per-day weather: cloud factor per zone + one overcast spell."""
    rng = random.Random(f"weather-{sim_day}")
    clouds = {z: rng.uniform(0.7, 1.0) for z in GRID_ZONES}
    spell_zone = rng.choice(GRID_ZONES)
    spell_start = rng.uniform(0.38, 0.50)
    return {"clouds": clouds, "spell_zone": spell_zone,
            "spell_start": spell_start, "spell_end": spell_start + OVERCAST_SPELL_LENGTH}


def simulate_reading(household_idx: int, tod_fraction: float, sim_day: int = 0, rng=random):
    zone = GRID_ZONES[household_idx % len(GRID_ZONES)]

    # Consumption: base load + morning/evening peaks (two bumps over the day)
    base_load = 0.15
    morning_peak = 0.5 * math.exp(-((tod_fraction - 0.30) ** 2) / (2 * 0.1 ** 2))
    evening_peak = 0.9 * math.exp(-((tod_fraction - 0.75) ** 2) / (2 * 0.15 ** 2))
    consumption = (base_load + morning_peak + evening_peak) * rng.uniform(0.7, 1.3)
    if rng.random() < 0.01:
        consumption *= rng.uniform(3, 6)  # legitimate short demand spike
    consumption = round(max(0.0, consumption), 3)

    # Solar: daylight bell curve centred at simulated noon, zero at night
    weather = daily_weather(sim_day)
    daylight = math.exp(-((tod_fraction - 0.5) ** 2) / (2 * 0.1 ** 2))
    cloud = weather["clouds"][zone]
    if zone == weather["spell_zone"] and weather["spell_start"] <= tod_fraction <= weather["spell_end"]:
        cloud *= 0.08  # heavy overcast spell
    solar = 0.35 * daylight * ZONE_SOLAR_CAPACITY[zone] * cloud * rng.uniform(0.85, 1.05)
    solar = round(max(0.0, solar), 3)

    return {
        "event_id": str(uuid.uuid4()),
        "meter_id": f"M-{household_idx:03d}",
        "household_id": f"H-{household_idx:03d}",
        "power_consumption_kwh": consumption,
        "solar_generation_kwh": solar,
        "grid_zone": zone,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def make_dirty(event: dict, kind: str) -> dict:
    """Corrupt a clean event in one of the ways real meter feeds go wrong."""
    bad = dict(event)
    if kind == "missing_field":
        bad["household_id"] = None
    elif kind == "negative_value":
        bad["power_consumption_kwh"] = -abs(event["power_consumption_kwh"]) - 0.1
    elif kind == "bad_timestamp":
        bad["timestamp"] = "not-a-timestamp"
    elif kind == "out_of_range":
        bad["power_consumption_kwh"] = 999.0
    # "duplicate" is the identical event, re-sent (handled by the caller)
    return bad


# ---------------------------------------------------------------------------
# Kafka plumbing
# ---------------------------------------------------------------------------
def ensure_topic():
    """Create the topic with an explicit partition count (idempotent)."""
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError

    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, client_id="topic-bootstrap")
    try:
        admin.create_topics([NewTopic(
            name=KAFKA_TOPIC_METER_READINGS,
            num_partitions=KAFKA_PARTITIONS,
            replication_factor=KAFKA_REPLICATION_FACTOR,
            topic_configs={"retention.ms": str(7 * 24 * 3600 * 1000)},
        )])
        log_event(logger, "info", "topic_created", topic=KAFKA_TOPIC_METER_READINGS, partitions=KAFKA_PARTITIONS)
    except TopicAlreadyExistsError:
        log_event(logger, "info", "topic_exists", topic=KAFKA_TOPIC_METER_READINGS)
    finally:
        admin.close()


def build_producer():
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable

    attempt = 0
    while True:
        try:
            ensure_topic()
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",           # wait for the (single) in-sync replica
                retries=5,
                linger_ms=50,         # small batching window
                max_in_flight_requests_per_connection=1,  # keep per-key ordering on retry
            )
        except NoBrokersAvailable:
            attempt += 1
            log_event(logger, "warning", "kafka_not_ready", attempt=attempt)
            time.sleep(min(2 * attempt, 15))


def run():
    from prometheus_client import Counter, Gauge, start_http_server

    from common.sim_clock import get_sim_epoch
    from observability.heartbeat import beat

    produced = Counter("meter_events_produced_total", "Events handed to the Kafka producer", ["kind"])
    delivered = Counter("meter_events_delivered_total", "Events acknowledged by Kafka")
    failed = Counter("meter_events_delivery_failed_total", "Events Kafka failed to acknowledge")
    last_send = Gauge("meter_producer_last_send_timestamp_seconds", "Unix time of the last send loop")
    start_http_server(PRODUCER_METRICS_PORT)

    epoch = get_sim_epoch()
    producer = build_producer()
    partitions = sorted(producer.partitions_for(KAFKA_TOPIC_METER_READINGS) or [])
    log_event(
        logger, "info", "producer_started",
        topic=KAFKA_TOPIC_METER_READINGS, partitions=partitions, num_households=NUM_HOUSEHOLDS,
        simulated_day_seconds=SIMULATED_DAY_SECONDS, dirty_event_rate=DIRTY_EVENT_RATE,
    )

    stop = {"flag": False}

    def _shutdown(signum, _frame):
        stop["flag"] = True
        log_event(logger, "info", "shutdown_requested", signal=signum)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    def _on_error(exc):
        failed.inc()
        log_event(logger, "error", "delivery_failed", error=str(exc))

    def send(event, kind):
        future = producer.send(KAFKA_TOPIC_METER_READINGS, key=event.get("household_id") or "unknown", value=event)
        future.add_callback(lambda _md: delivered.inc())
        future.add_errback(_on_error)
        produced.labels(kind=kind).inc()

    loops = 0
    redeliveries = []  # (due_loop, event): duplicates re-sent a few seconds later, like a producer retry
    while not stop["flag"]:
        now = time.time()
        tod, sim_day = day_fraction_at(now, epoch), sim_day_at(now, epoch)
        for due, event in [r for r in redeliveries if r[0] <= loops]:
            send(event, "duplicate")
        redeliveries = [r for r in redeliveries if r[0] > loops]
        for h in range(NUM_HOUSEHOLDS):
            event = simulate_reading(h, tod, sim_day)
            try:
                if random.random() < DIRTY_EVENT_RATE:
                    kind = random.choice(DIRTY_KINDS)
                    if kind == "duplicate":
                        send(event, "clean")
                        # redelivered 1-5 loops (2-10 s) later: may land in a later
                        # micro-batch, where only the batch layer's global dedup catches it
                        redeliveries.append((loops + random.randint(1, 5), event))
                    else:
                        send(make_dirty(event, kind), kind)
                else:
                    send(event, "clean")
            except Exception as exc:  # noqa: BLE001 - log and keep the stream alive
                failed.inc()
                log_event(logger, "error", "produce_failed", household_id=event["household_id"], error=str(exc))

        loops += 1
        last_send.set(now)
        if loops % 5 == 0:
            producer.flush(timeout=10)
            log_event(
                logger, "info", "producer_heartbeat", sim_day=sim_day, day_fraction=round(tod, 3),
                delivered_total=delivered._value.get(), failed_total=failed._value.get(),
            )
            beat("meter_producer", f"sim_day={sim_day} delivered={int(delivered._value.get())}", logger=logger)
        time.sleep(METER_EMIT_INTERVAL_SECONDS)

    producer.flush(timeout=10)
    producer.close()
    log_event(logger, "info", "producer_stopped")


if __name__ == "__main__":
    run()
