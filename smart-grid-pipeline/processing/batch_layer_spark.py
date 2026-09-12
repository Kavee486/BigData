"""Batch layer: daily reconciliation & billing job (Lambda's "batch view").

Orchestrated once per simulated day by Airflow. For a given sim_day it:

  1. Reads that day's partition of the raw-event Parquet lake
     (the immutable append-only log written by the speed layer) and
     recomputes accurate per-household daily totals -- this is the
     "batch view" that supersedes the speed layer's approximate windows.
  2. Reads the tariff/billing CSV dropped by the daily-batch source.
  3. Joins consumption totals with tariff data, applies billing rules
     (net consumption after solar export, subsidy discount), and writes
     the consolidated daily_billing_report to Postgres.

Usage:
    spark-submit ... processing/batch_layer_spark.py --sim-day 3 --tariff-file /data/batch_drop/tariff_...csv
"""
import argparse
import sys

sys.path.append("/app")
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from config import RAW_EVENTS_PATH, POSTGRES_JDBC_URL, POSTGRES_USER, POSTGRES_PASSWORD, pg_dsn
from observability.logging_config import get_logger, log_event
from processing.billing_rules import SUBSIDY_DISCOUNT_PCT

logger = get_logger("batch_layer")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-day", type=int, required=True)
    p.add_argument("--tariff-file", type=str, required=True)
    return p.parse_args()


def upsert_household_daily(spark, sim_day: int):
    """Recompute per-household daily consumption from the raw Parquet lake."""
    raw = spark.read.parquet(RAW_EVENTS_PATH).where(F.col("sim_day") == sim_day)

    daily = (
        raw.groupBy("household_id", "grid_zone")
        .agg(
            F.sum("power_consumption_kwh").alias("total_consumption_kwh"),
            F.sum("solar_generation_kwh").alias("total_solar_kwh"),
            F.count("*").alias("reading_count"),
        )
        .withColumn(
            "net_consumption_kwh",
            F.greatest(F.col("total_consumption_kwh") - F.col("total_solar_kwh"), F.lit(0.0)),
        )
        .withColumn("sim_day", F.lit(sim_day))
    )

    count = daily.count()
    log_event(logger, "info", "household_daily_recomputed", sim_day=sim_day, households=count)

    rows = daily.collect()
    import psycopg2

    conn = psycopg2.connect(pg_dsn())
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO household_daily_consumption (
                household_id, sim_day, grid_zone, total_consumption_kwh,
                total_solar_kwh, net_consumption_kwh, reading_count, computed_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (household_id, sim_day) DO UPDATE SET
                grid_zone = EXCLUDED.grid_zone,
                total_consumption_kwh = EXCLUDED.total_consumption_kwh,
                total_solar_kwh = EXCLUDED.total_solar_kwh,
                net_consumption_kwh = EXCLUDED.net_consumption_kwh,
                reading_count = EXCLUDED.reading_count,
                computed_at = now();
            """,
            (
                r["household_id"], sim_day, r["grid_zone"], r["total_consumption_kwh"],
                r["total_solar_kwh"], r["net_consumption_kwh"], int(r["reading_count"]),
            ),
        )
    conn.commit()
    cur.close()
    conn.close()
    return count


def load_tariff_reference(spark, tariff_file: str, sim_day: int):
    tariff = (
        spark.read.option("header", True).option("inferSchema", True).csv(tariff_file)
        .withColumn("day", F.col("day").cast("int"))
    )

    rows = tariff.collect()
    import psycopg2

    conn = psycopg2.connect(pg_dsn())
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO tariff_reference (household_id, sim_day, tariff_rate, billing_tier, subsidy_flag, loaded_at)
            VALUES (%s,%s,%s,%s,%s, now())
            ON CONFLICT (household_id, sim_day) DO UPDATE SET
                tariff_rate = EXCLUDED.tariff_rate,
                billing_tier = EXCLUDED.billing_tier,
                subsidy_flag = EXCLUDED.subsidy_flag,
                loaded_at = now();
            """,
            (r["household_id"], sim_day, r["tariff_rate"], r["billing_tier"], bool(r["subsidy_flag"])),
        )
    conn.commit()
    cur.close()
    conn.close()
    log_event(logger, "info", "tariff_reference_loaded", sim_day=sim_day, rows=len(rows))
    return len(rows)


def compute_billing_report(spark, sim_day: int):
    """Join consumption + tariff (both already in Postgres) and write the bill."""
    jdbc_opts = dict(url=POSTGRES_JDBC_URL, user=POSTGRES_USER, password=POSTGRES_PASSWORD,
                      driver="org.postgresql.Driver")

    consumption = spark.read.format("jdbc").options(
        dbtable=f"(SELECT * FROM household_daily_consumption WHERE sim_day = {sim_day}) t", **jdbc_opts
    ).load()
    tariff = spark.read.format("jdbc").options(
        dbtable=f"(SELECT * FROM tariff_reference WHERE sim_day = {sim_day}) t", **jdbc_opts
    ).load()

    joined = consumption.join(tariff, on=["household_id", "sim_day"], how="inner")

    billed = (
        joined.withColumn(
            "subsidy_discount_pct",
            F.when(F.col("subsidy_flag"), F.lit(SUBSIDY_DISCOUNT_PCT)).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "bill_amount",
            F.round(
                F.col("net_consumption_kwh") * F.col("tariff_rate")
                * (1 - F.col("subsidy_discount_pct") / 100.0),
                2,
            ),
        )
        .select(
            "household_id", "sim_day", "grid_zone", "total_consumption_kwh",
            "total_solar_kwh", "net_consumption_kwh", "tariff_rate", "billing_tier",
            "subsidy_flag", "subsidy_discount_pct", "bill_amount",
        )
    )

    rows = billed.collect()
    import psycopg2

    conn = psycopg2.connect(pg_dsn())
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """
            INSERT INTO daily_billing_report (
                household_id, sim_day, grid_zone, total_consumption_kwh, total_solar_kwh,
                net_consumption_kwh, tariff_rate, billing_tier, subsidy_flag,
                subsidy_discount_pct, bill_amount, generated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (household_id, sim_day) DO UPDATE SET
                total_consumption_kwh = EXCLUDED.total_consumption_kwh,
                total_solar_kwh = EXCLUDED.total_solar_kwh,
                net_consumption_kwh = EXCLUDED.net_consumption_kwh,
                tariff_rate = EXCLUDED.tariff_rate,
                billing_tier = EXCLUDED.billing_tier,
                subsidy_flag = EXCLUDED.subsidy_flag,
                subsidy_discount_pct = EXCLUDED.subsidy_discount_pct,
                bill_amount = EXCLUDED.bill_amount,
                generated_at = now();
            """,
            (
                r["household_id"], sim_day, r["grid_zone"], r["total_consumption_kwh"],
                r["total_solar_kwh"], r["net_consumption_kwh"], r["tariff_rate"],
                r["billing_tier"], bool(r["subsidy_flag"]), r["subsidy_discount_pct"], r["bill_amount"],
            ),
        )
    cur.execute(
        """
        INSERT INTO pipeline_health (component, last_heartbeat, status, detail)
        VALUES ('batch_layer', now(), 'OK', %s)
        ON CONFLICT (component) DO UPDATE SET last_heartbeat = now(), status = 'OK', detail = EXCLUDED.detail;
        """,
        (f"sim_day={sim_day} households_billed={len(rows)}",),
    )
    conn.commit()
    cur.close()
    conn.close()

    log_event(logger, "info", "billing_report_generated", sim_day=sim_day, households=len(rows))
    return len(rows)


def main():
    args = parse_args()
    spark = SparkSession.builder.appName("smart-grid-batch-layer").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    try:
        n_hh = upsert_household_daily(spark, args.sim_day)
        n_tariff = load_tariff_reference(spark, args.tariff_file, args.sim_day)
        n_bills = compute_billing_report(spark, args.sim_day)
        log_event(
            logger, "info", "batch_layer_run_complete",
            sim_day=args.sim_day, households=n_hh, tariff_rows=n_tariff, bills=n_bills,
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "error", "batch_layer_run_failed", sim_day=args.sim_day, error=str(exc))
        raise


if __name__ == "__main__":
    main()
