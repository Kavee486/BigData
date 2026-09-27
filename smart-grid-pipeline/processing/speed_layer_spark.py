"""Speed layer: Spark Structured Streaming over Kafka.

Two streaming queries share one parsed + validated event stream:

  1. zone_metrics (stateful, event-time):
     clean events -> 1-minute watermark -> 30s window sliding every 15s,
     grouped by grid_zone -> load, solar, renewable % -> idempotent upsert
     into Postgres `live_zone_metrics`. Serves /api/grid/live and the
     LOW_RENEWABLE alert.

  2. raw_lake (foreachBatch, one pass per micro-batch):
       a. invalid events (see processing/quality_rules.py) -> quarantine
          Parquet with their reason code (never silently dropped);
       b. clean events, deduplicated on event_id within the micro-batch,
          are appended to the immutable raw Parquet lake partitioned by
          sim_day (derived from EVENT time via the shared sim clock) -- the
          batch layer's source of truth;
       c. per-household running totals for the current sim_day are added
          into `live_household_consumption` -- the speed-layer half of the
          provisional bill that the API merges with the batch view;
       d. data-quality and lag figures go to `stream_quality_metrics`.

This layer is deliberately "fast but approximate": dedup is only within a
micro-batch and the running totals are additive, so a Kafka redelivery after
a crash can double count. The batch layer recomputes each day exactly (global
dedup on event_id) and the reconciliation table measures the difference --
that division of labour is the Lambda architecture.

Run with:
    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,\
        org.postgresql:postgresql:42.7.3 processing/speed_layer_spark.py
"""
import os
import sys
import time

sys.path.append("/app")
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

from common.sim_clock import get_sim_epoch
from config import (
    CHECKPOINT_ROOT,
    GRID_ZONES,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_METER_READINGS,
    QUARANTINE_PATH,
    RAW_EVENTS_PATH,
    SIMULATED_DAY_SECONDS,
    SPEED_LAYER_SLIDE,
    SPEED_LAYER_TRIGGER,
    SPEED_LAYER_WATERMARK,
    SPEED_LAYER_WINDOW,
    pg_dsn,
)
from observability.logging_config import get_logger, log_event
from processing import quality_rules as Q

logger = get_logger("speed_layer")

EVENT_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("meter_id", StringType()),
    StructField("household_id", StringType()),
    StructField("power_consumption_kwh", DoubleType()),
    StructField("solar_generation_kwh", DoubleType()),
    StructField("grid_zone", StringType()),
    StructField("timestamp", StringType()),
])


def invalid_reason_col():
    """Spark mirror of quality_rules.validate_event (same rules, same order)."""
    missing = None
    for field in Q.REQUIRED_FIELDS:
        cond = F.col(field).isNull() | (F.col(field) == "")
        missing = cond if missing is None else (missing | cond)
    missing = missing | F.col("power_consumption_kwh").isNull() | F.col("solar_generation_kwh").isNull()
    return (
        F.when(missing, F.lit(Q.MISSING_FIELD))
        .when(F.col("event_time").isNull(), F.lit(Q.BAD_TIMESTAMP))
        .when(~F.col("grid_zone").isin(GRID_ZONES), F.lit(Q.UNKNOWN_ZONE))
        .when((F.col("power_consumption_kwh") < 0) | (F.col("solar_generation_kwh") < 0), F.lit(Q.NEGATIVE_VALUE))
        .when((F.col("power_consumption_kwh") > Q.MAX_READING_KWH)
              | (F.col("solar_generation_kwh") > Q.MAX_READING_KWH), F.lit(Q.OUT_OF_RANGE))
        .otherwise(F.lit(None).cast("string"))
    )


def _pg():
    import psycopg2
    return psycopg2.connect(pg_dsn())


def write_zone_metrics(batch_df, batch_id: int):
    """foreachBatch sink for the windowed aggregate: idempotent upsert."""
    rows = batch_df.collect()
    if not rows:
        return
    # A handful of zone-window rows per micro-batch: a psycopg2 upsert
    # (ON CONFLICT) is simpler and cheaper than Spark JDBC + a staging table,
    # and makes replays of the same window idempotent.
    from psycopg2.extras import execute_values

    conn = _pg()
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO live_zone_metrics (
                    grid_zone, window_start, window_end, avg_consumption_kwh,
                    avg_solar_kwh, total_consumption_kwh, total_solar_kwh,
                    renewable_pct, event_count, household_count, updated_at
                ) VALUES %s
                ON CONFLICT (grid_zone, window_start) DO UPDATE SET
                    window_end = EXCLUDED.window_end,
                    avg_consumption_kwh = EXCLUDED.avg_consumption_kwh,
                    avg_solar_kwh = EXCLUDED.avg_solar_kwh,
                    total_consumption_kwh = EXCLUDED.total_consumption_kwh,
                    total_solar_kwh = EXCLUDED.total_solar_kwh,
                    renewable_pct = EXCLUDED.renewable_pct,
                    event_count = EXCLUDED.event_count,
                    household_count = EXCLUDED.household_count,
                    updated_at = now();
                """,
                [(r["grid_zone"], r["window_start"], r["window_end"], r["avg_consumption_kwh"],
                  r["avg_solar_kwh"], r["total_consumption_kwh"], r["total_solar_kwh"],
                  r["renewable_pct"], int(r["event_count"]), int(r["household_count"])) for r in rows],
                template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())",
            )
            # Housekeeping: the live table only needs recent windows.
            cur.execute("DELETE FROM live_zone_metrics WHERE window_start < now() - interval '6 hours';")
        conn.commit()
    finally:
        conn.close()
    log_event(logger, "info", "zone_metrics_written", batch_id=batch_id, rows=len(rows))


def make_lake_writer(epoch: float):
    def write_lake_and_running_totals(batch_df, batch_id: int):
        started = time.time()
        df = batch_df.withColumn("invalid_reason", invalid_reason_col()).persist()
        try:
            total = df.count()
            if total == 0:
                return
            invalid = df.where(F.col("invalid_reason").isNotNull())
            clean = (
                df.where(F.col("invalid_reason").isNull())
                .dropDuplicates(["event_id"])
                .withColumn(
                    "sim_day",
                    F.floor((F.col("event_time").cast("double") - F.lit(epoch)) / F.lit(SIMULATED_DAY_SECONDS)).cast("int"),
                )
                .where(F.col("sim_day") >= 0)
                .drop("invalid_reason")
                .persist()
            )
            clean_count = clean.count()
            invalid_count = invalid.count()
            duplicates = total - invalid_count - clean_count

            # (a) quarantine -- keep the raw payload for diagnosis
            if invalid_count:
                (invalid.withColumn("quarantined_at", F.current_timestamp())
                 .write.mode("append").partitionBy("invalid_reason").parquet(QUARANTINE_PATH))

            # (b) immutable raw lake, partitioned by event-time sim_day
            clean.write.mode("append").partitionBy("sim_day").parquet(RAW_EVENTS_PATH)

            # (c) per-household running totals (speed view of "today")
            per_household = (
                clean.groupBy("household_id", "sim_day", "grid_zone")
                .agg(F.sum("power_consumption_kwh").alias("c"), F.sum("solar_generation_kwh").alias("s"),
                     F.count("*").alias("n"), F.max("event_time").alias("last_event_time"))
                .collect()
            )
            lag = clean.agg(
                F.avg(F.lit(started) - F.col("event_time").cast("double")).alias("avg_lag"),
                F.max(F.lit(started) - F.col("event_time").cast("double")).alias("max_lag"),
            ).collect()[0]
            invalid_by_reason = {r["invalid_reason"]: r["count"]
                                 for r in invalid.groupBy("invalid_reason").count().collect()}

            from psycopg2.extras import Json, execute_values
            conn = _pg()
            try:
                with conn.cursor() as cur:
                    if per_household:
                        execute_values(cur, """
                            INSERT INTO live_household_consumption (
                                household_id, sim_day, grid_zone, consumption_kwh, solar_kwh,
                                reading_count, last_event_time, updated_at)
                            VALUES %s
                            ON CONFLICT (household_id, sim_day) DO UPDATE SET
                                consumption_kwh = live_household_consumption.consumption_kwh + EXCLUDED.consumption_kwh,
                                solar_kwh = live_household_consumption.solar_kwh + EXCLUDED.solar_kwh,
                                reading_count = live_household_consumption.reading_count + EXCLUDED.reading_count,
                                last_event_time = GREATEST(live_household_consumption.last_event_time, EXCLUDED.last_event_time),
                                updated_at = now();
                            """,
                            [(r["household_id"], r["sim_day"], r["grid_zone"], r["c"], r["s"], int(r["n"]),
                              r["last_event_time"]) for r in per_household],
                            template="(%s,%s,%s,%s,%s,%s,%s, now())",
                        )
                    cur.execute(
                        """
                        INSERT INTO stream_quality_metrics (
                            batch_id, total_events, clean_events, invalid_events, duplicate_events,
                            invalid_by_reason, avg_lag_seconds, max_lag_seconds, processing_seconds)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);
                        """,
                        (batch_id, total, clean_count, invalid_count, duplicates, Json(invalid_by_reason),
                         lag["avg_lag"], lag["max_lag"], round(time.time() - started, 3)),
                    )
                    cur.execute("DELETE FROM stream_quality_metrics WHERE recorded_at < now() - interval '6 hours';")
                    cur.execute(
                        """
                        INSERT INTO pipeline_health (component, last_heartbeat, status, detail)
                        VALUES ('speed_layer', now(), 'OK', %s)
                        ON CONFLICT (component) DO UPDATE SET
                            last_heartbeat = now(), status = 'OK', detail = EXCLUDED.detail;
                        """,
                        (f"batch_id={batch_id} clean={clean_count} invalid={invalid_count} dup={duplicates}",),
                    )
                conn.commit()
            finally:
                conn.close()

            clean.unpersist()
            log_event(
                logger, "info", "micro_batch_processed", batch_id=batch_id, total=total, clean=clean_count,
                invalid=invalid_count, duplicates=duplicates, invalid_by_reason=invalid_by_reason,
                avg_lag_s=round(lag["avg_lag"] or 0, 2), processing_s=round(time.time() - started, 2),
            )
        except Exception as exc:  # noqa: BLE001 - log with context, then let Spark retry/fail the query
            log_event(logger, "error", "micro_batch_failed", batch_id=batch_id, error=str(exc))
            raise
        finally:
            df.unpersist()

    return write_lake_and_running_totals


def main():
    epoch = get_sim_epoch()
    spark = (
        SparkSession.builder.appName("smart-grid-speed-layer")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC_METER_READINGS)
        # earliest + checkpoints: nothing produced before Spark came up is lost
        # from the lake, and restarts resume from the committed offsets.
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", "20000")
        .load()
    )

    events = (
        raw.select(F.col("value").cast("string").alias("json_str"), F.col("partition"), F.col("offset"))
        .select(F.from_json("json_str", EVENT_SCHEMA).alias("e"), "json_str", "partition", "offset")
        .select("e.*", "json_str", "partition", "offset")
        .withColumn("event_time", F.to_timestamp("timestamp"))
    )

    # --- Query 1: windowed zone aggregation on clean events (real-time view) ---
    clean_events = events.where(invalid_reason_col().isNull())
    windowed = (
        clean_events.withWatermark("event_time", SPEED_LAYER_WATERMARK)
        .groupBy(F.window("event_time", SPEED_LAYER_WINDOW, SPEED_LAYER_SLIDE), F.col("grid_zone"))
        .agg(
            F.avg("power_consumption_kwh").alias("avg_consumption_kwh"),
            F.avg("solar_generation_kwh").alias("avg_solar_kwh"),
            F.sum("power_consumption_kwh").alias("total_consumption_kwh"),
            F.sum("solar_generation_kwh").alias("total_solar_kwh"),
            F.count("*").alias("event_count"),
            F.approx_count_distinct("household_id").alias("household_count"),
        )
        # Renewable contribution = share of the zone's demand met by solar.
        .withColumn(
            "renewable_pct",
            F.when(F.col("total_consumption_kwh") > 0,
                   F.least(F.lit(100.0), 100.0 * F.col("total_solar_kwh") / F.col("total_consumption_kwh")))
            .otherwise(F.lit(0.0)),
        )
        .select(
            "grid_zone",
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "avg_consumption_kwh", "avg_solar_kwh", "total_consumption_kwh", "total_solar_kwh",
            "renewable_pct", "event_count", "household_count",
        )
    )
    (
        windowed.writeStream.queryName("zone_metrics").outputMode("update")
        .foreachBatch(write_zone_metrics)
        .trigger(processingTime=SPEED_LAYER_TRIGGER)
        .option("checkpointLocation", os.path.join(CHECKPOINT_ROOT, "zone_metrics"))
        .start()
    )

    # --- Query 2: quarantine + raw lake + running household totals ---
    (
        events.writeStream.queryName("raw_lake")
        .foreachBatch(make_lake_writer(epoch))
        .trigger(processingTime=SPEED_LAYER_TRIGGER)
        .option("checkpointLocation", os.path.join(CHECKPOINT_ROOT, "raw_lake"))
        .start()
    )

    log_event(logger, "info", "speed_layer_started", window=SPEED_LAYER_WINDOW, slide=SPEED_LAYER_SLIDE,
              watermark=SPEED_LAYER_WATERMARK, sim_epoch=epoch)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
