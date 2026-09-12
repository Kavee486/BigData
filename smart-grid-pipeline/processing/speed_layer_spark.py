"""Speed layer: Spark Structured Streaming.

Reads raw smart-meter events from Kafka and produces two outputs per
micro-batch (foreachBatch):

  1. Real-time (approximate) zone-level metrics -> Postgres `live_zone_metrics`
     table, via a sliding window aggregation. This is what the API's
     /api/grid/live endpoint serves.
  2. An append-only archive of every raw event -> Parquet data lake
     (RAW_EVENTS_PATH, partitioned by sim_day). This is the immutable log
     the *batch* layer recomputes the accurate daily billing report from,
     which is the defining trait of a Lambda architecture: the speed layer
     is a fast/approximate view, the batch layer is the accurate one.

Run with:
    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,\
                  org.postgresql:postgresql:42.7.3 processing/speed_layer_spark.py
"""
import sys
import time

sys.path.append("/app")
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType
)

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_METER_READINGS,
    POSTGRES_JDBC_URL,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    RAW_EVENTS_PATH,
    SIMULATED_DAY_SECONDS,
    SPEED_LAYER_WINDOW,
    SPEED_LAYER_SLIDE,
    SPEED_LAYER_WATERMARK,
)
from observability.logging_config import get_logger, log_event

logger = get_logger("speed_layer")

EVENT_SCHEMA = StructType([
    StructField("meter_id", StringType()),
    StructField("household_id", StringType()),
    StructField("power_consumption_kwh", DoubleType()),
    StructField("solar_generation_kwh", DoubleType()),
    StructField("grid_zone", StringType()),
    StructField("timestamp", StringType()),
])

PIPELINE_START = time.time()


def sim_day_col():
    """Derive the simulated-day number from wall-clock elapsed time.

    Kept as a Python UDF-free expression so it runs efficiently in
    foreachBatch on the driver-collected small aggregate frame.
    """
    elapsed = time.time() - PIPELINE_START
    return int(elapsed // SIMULATED_DAY_SECONDS)


def write_zone_metrics(batch_df, batch_id: int):
    if batch_df.rdd.isEmpty():
        return
    # Zone-window aggregates are a handful of rows per micro-batch, so a
    # plain psycopg2 upsert (ON CONFLICT) is simpler and cheaper here than
    # routing through Spark's JDBC writer + a separate staging table.
    import psycopg2
    from config import pg_dsn

    rows = batch_df.collect()
    conn = psycopg2.connect(pg_dsn())
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO live_zone_metrics (
                grid_zone, window_start, window_end, avg_consumption_kwh,
                avg_solar_kwh, total_consumption_kwh, total_solar_kwh,
                renewable_pct, event_count, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (grid_zone, window_start) DO UPDATE SET
                window_end = EXCLUDED.window_end,
                avg_consumption_kwh = EXCLUDED.avg_consumption_kwh,
                avg_solar_kwh = EXCLUDED.avg_solar_kwh,
                total_consumption_kwh = EXCLUDED.total_consumption_kwh,
                total_solar_kwh = EXCLUDED.total_solar_kwh,
                renewable_pct = EXCLUDED.renewable_pct,
                event_count = EXCLUDED.event_count,
                updated_at = now();
            """,
            (
                r["grid_zone"], r["window_start"], r["window_end"],
                r["avg_consumption_kwh"], r["avg_solar_kwh"],
                r["total_consumption_kwh"], r["total_solar_kwh"],
                r["renewable_pct"], int(r["event_count"]),
            ),
        )
    cur.execute(
        """
        INSERT INTO pipeline_health (component, last_heartbeat, status, detail)
        VALUES ('speed_layer', now(), 'OK', %s)
        ON CONFLICT (component) DO UPDATE SET
            last_heartbeat = now(), status = 'OK', detail = EXCLUDED.detail;
        """,
        (f"batch_id={batch_id} rows={len(rows)}",),
    )
    conn.commit()
    cur.close()
    conn.close()

    log_event(logger, "info", "zone_metrics_written", batch_id=batch_id, rows=len(rows))


def main():
    spark = (
        SparkSession.builder.appName("smart-grid-speed-layer")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC_METER_READINGS)
        .option("startingOffsets", "latest")
        .load()
    )

    events = (
        raw.select(F.col("value").cast("string").alias("json_str"))
        .select(F.from_json("json_str", EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_time", F.to_timestamp("timestamp"))
        .withColumn("power_consumption_kwh", F.coalesce(F.col("power_consumption_kwh"), F.lit(0.0)))
        .withColumn("solar_generation_kwh", F.coalesce(F.col("solar_generation_kwh"), F.lit(0.0)))
    )

    # --- Output 1: windowed zone aggregation (real-time / approximate view) ---
    windowed = (
        events.withWatermark("event_time", SPEED_LAYER_WATERMARK)
        .groupBy(F.window("event_time", SPEED_LAYER_WINDOW, SPEED_LAYER_SLIDE), F.col("grid_zone"))
        .agg(
            F.avg("power_consumption_kwh").alias("avg_consumption_kwh"),
            F.avg("solar_generation_kwh").alias("avg_solar_kwh"),
            F.sum("power_consumption_kwh").alias("total_consumption_kwh"),
            F.sum("solar_generation_kwh").alias("total_solar_kwh"),
            F.count("*").alias("event_count"),
        )
        .withColumn(
            "renewable_pct",
            F.when(
                (F.col("total_consumption_kwh") + F.col("total_solar_kwh")) > 0,
                100.0 * F.col("total_solar_kwh") / (F.col("total_consumption_kwh") + F.col("total_solar_kwh")),
            ).otherwise(F.lit(0.0)),
        )
        .select(
            F.col("grid_zone"),
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "avg_consumption_kwh", "avg_solar_kwh",
            "total_consumption_kwh", "total_solar_kwh",
            "renewable_pct", "event_count",
        )
    )

    zone_query = (
        windowed.writeStream.outputMode("update")
        .foreachBatch(write_zone_metrics)
        .trigger(processingTime="10 seconds")
        .option("checkpointLocation", "/data/checkpoints/zone_metrics")
        .start()
    )

    # --- Output 2: append raw events to the Parquet data lake (batch layer's source of truth) ---
    lake_query = (
        events.withColumn("sim_day", F.lit(None).cast("int"))  # placeholder, overwritten below via foreachBatch
        .writeStream.foreachBatch(
            lambda df, bid: (
                df.drop("sim_day")
                .withColumn("sim_day", F.lit(sim_day_col()))
                .write.mode("append")
                .partitionBy("sim_day")
                .parquet(RAW_EVENTS_PATH)
            )
        )
        .trigger(processingTime="10 seconds")
        .option("checkpointLocation", "/data/checkpoints/raw_lake")
        .start()
    )

    log_event(logger, "info", "speed_layer_started", window=SPEED_LAYER_WINDOW, slide=SPEED_LAYER_SLIDE)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
