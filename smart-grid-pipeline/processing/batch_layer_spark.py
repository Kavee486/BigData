"""Batch layer: exact daily recomputation + tariff join + billing (Lambda "batch view").

Orchestrated by Airflow once a simulated day has ended and its tariff extract
has landed. For --sim-day N it:

  1. Reads ONLY partition sim_day=N of the immutable raw Parquet lake and
     removes duplicates GLOBALLY on event_id (the speed layer can only dedup
     within a micro-batch) -> exact per-household daily totals.
  2. Reads the day's tariff CSV with an explicit schema, rejects invalid rows
     (blank / non-numeric / non-positive rate, unknown tier), de-duplicates
     households, and for any household left without a valid tariff falls back
     to its most recent valid tariff from previous days (enrichment).
  3. Joins consumption with tariff on household_id and applies the billing
     formula (processing/billing_rules.py) -> daily_billing_report.
  4. Reconciles the exact batch totals against the speed layer's running
     totals for the same day -> batch_reconciliation (drift %).

All of a day's outputs are replaced inside ONE Postgres transaction
(delete-then-insert for sim_day = N), so a re-run/backfill is idempotent and
readers never see a half-written day.

Usage:
    spark-submit processing/batch_layer_spark.py --sim-day 3 --tariff-file /data/batch_drop/tariff_simday3.csv
"""
import argparse
import sys
import time
import uuid

sys.path.append("/app")
import psycopg2
from psycopg2.extras import execute_values
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from config import RAW_EVENTS_PATH, pg_dsn
from observability.heartbeat import beat
from observability.logging_config import get_logger, log_event
from processing.billing_rules import SUBSIDY_DISCOUNT_PCT

logger = get_logger("batch_layer")

VALID_TIERS = ["residential_low", "residential_standard", "residential_high"]
TARIFF_SCHEMA = StructType([StructField(c, StringType()) for c in
                            ["household_id", "tariff_rate", "billing_tier", "subsidy_flag", "sim_day", "published_at"]])


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-day", type=int, required=True)
    p.add_argument("--tariff-file", type=str, required=True)
    return p.parse_args()


# ---------------------------------------------------------------------------
# 1. Exact consumption view from the raw lake
# ---------------------------------------------------------------------------
def compute_household_daily(spark, sim_day: int):
    raw = spark.read.parquet(RAW_EVENTS_PATH).where(F.col("sim_day") == sim_day)
    raw_count = raw.count()
    if raw_count == 0:
        raise RuntimeError(f"no raw events in the lake for sim_day={sim_day}")
    deduped = raw.dropDuplicates(["event_id"])
    dedup_count = deduped.count()

    daily = (
        deduped.groupBy("household_id", "grid_zone")
        .agg(
            F.sum("power_consumption_kwh").alias("total_consumption_kwh"),
            F.sum("solar_generation_kwh").alias("total_solar_kwh"),
            F.max("power_consumption_kwh").alias("peak_reading_kwh"),
            F.count("*").alias("reading_count"),
        )
        .withColumn("net_consumption_kwh",
                    F.greatest(F.col("total_consumption_kwh") - F.col("total_solar_kwh"), F.lit(0.0)))
        .withColumn("solar_export_kwh",
                    F.greatest(F.col("total_solar_kwh") - F.col("total_consumption_kwh"), F.lit(0.0)))
        .withColumn(
            "solar_contribution_pct",
            F.when(F.col("total_consumption_kwh") > 0,
                   F.round(100.0 * F.least(F.col("total_solar_kwh"), F.col("total_consumption_kwh"))
                           / F.col("total_consumption_kwh"), 2)).otherwise(F.lit(0.0)),
        )
    )
    stats = {"raw_events": raw_count, "duplicates_removed": raw_count - dedup_count}
    log_event(logger, "info", "household_daily_recomputed", sim_day=sim_day, **stats)
    return daily, stats


# ---------------------------------------------------------------------------
# 2. Tariff: validate, dedupe, fall back to last known valid tariff
# ---------------------------------------------------------------------------
def previous_tariffs(spark, sim_day: int):
    """Latest valid tariff per household from days before sim_day (from Postgres)."""
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (household_id) household_id, tariff_rate, billing_tier, subsidy_flag
                FROM tariff_reference WHERE sim_day < %s
                ORDER BY household_id, sim_day DESC;
                """,
                (sim_day,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    schema = "household_id string, prev_tariff_rate double, prev_billing_tier string, prev_subsidy_flag boolean"
    return spark.createDataFrame(rows, schema)


def load_tariff(spark, tariff_file: str, sim_day: int):
    raw = spark.read.option("header", True).schema(TARIFF_SCHEMA).csv(tariff_file)
    typed = (
        raw.withColumn("tariff_rate_num", F.col("tariff_rate").cast("double"))
        .withColumn("subsidy_bool", F.lower(F.col("subsidy_flag")).isin("true", "1", "yes"))
    )
    is_valid = (
        F.col("household_id").isNotNull()
        & F.col("tariff_rate_num").isNotNull() & (F.col("tariff_rate_num") > 0)
        & F.col("billing_tier").isin(VALID_TIERS)
    )
    total_rows = typed.count()
    invalid_rows = typed.where(~is_valid).select("household_id", "tariff_rate").collect()
    valid = (
        typed.where(is_valid)
        .withColumn("rn", F.row_number().over(Window.partitionBy("household_id").orderBy(F.col("published_at").desc())))
        .where(F.col("rn") == 1)
        .select("household_id", F.col("tariff_rate_num").alias("tariff_rate"), "billing_tier",
                F.col("subsidy_bool").alias("subsidy_flag"))
    )
    valid_count = valid.count()
    stats = {
        "tariff_rows": total_rows,
        "invalid_tariff_rows": len(invalid_rows),
        "duplicate_tariff_rows": total_rows - len(invalid_rows) - valid_count,
    }
    if invalid_rows:
        log_event(logger, "warning", "tariff_rows_rejected", sim_day=sim_day,
                  rows=[{"household_id": r["household_id"], "tariff_rate": r["tariff_rate"]} for r in invalid_rows])
    log_event(logger, "info", "tariff_loaded", sim_day=sim_day, valid=valid_count, **stats)
    return valid, stats


# ---------------------------------------------------------------------------
# 3. Join + bill
# ---------------------------------------------------------------------------
def compute_bills(daily, tariff_today, tariff_prev):
    joined = daily.join(tariff_today, "household_id", "left").join(tariff_prev, "household_id", "left")
    enriched = (
        joined.withColumn("tariff_source",
                          F.when(F.col("tariff_rate").isNotNull(), F.lit("current_day"))
                          .when(F.col("prev_tariff_rate").isNotNull(), F.lit("fallback_previous_day"))
                          .otherwise(F.lit("missing")))
        .withColumn("tariff_rate", F.coalesce("tariff_rate", "prev_tariff_rate"))
        .withColumn("billing_tier", F.coalesce("billing_tier", "prev_billing_tier"))
        .withColumn("subsidy_flag", F.coalesce("subsidy_flag", "prev_subsidy_flag"))
    )
    # Same formula as processing/billing_rules.compute_bill (verified by scripts/smoke_test.py)
    return (
        enriched.where(F.col("tariff_source") != "missing")
        .withColumn("subsidy_discount_pct",
                    F.when(F.col("subsidy_flag"), F.lit(SUBSIDY_DISCOUNT_PCT)).otherwise(F.lit(0.0)))
        .withColumn("bill_amount",
                    F.round(F.col("net_consumption_kwh") * F.col("tariff_rate")
                            * (1 - F.col("subsidy_discount_pct") / 100.0), 2))
    ), enriched.where(F.col("tariff_source") == "missing").select("household_id").collect()


# ---------------------------------------------------------------------------
# 4. Persist the whole day atomically + reconcile against the speed layer
# ---------------------------------------------------------------------------
def persist_day(sim_day, run_id, daily_rows, tariff_rows, bill_rows, stats):
    conn = psycopg2.connect(pg_dsn())
    try:
        with conn.cursor() as cur:
            for table in ("household_daily_consumption", "tariff_reference", "daily_billing_report"):
                cur.execute(f"DELETE FROM {table} WHERE sim_day = %s;", (sim_day,))
            execute_values(cur, """
                INSERT INTO household_daily_consumption (household_id, sim_day, grid_zone, total_consumption_kwh,
                    total_solar_kwh, net_consumption_kwh, solar_export_kwh, solar_contribution_pct,
                    peak_reading_kwh, reading_count) VALUES %s""",
                [(r["household_id"], sim_day, r["grid_zone"], r["total_consumption_kwh"], r["total_solar_kwh"],
                  r["net_consumption_kwh"], r["solar_export_kwh"], r["solar_contribution_pct"],
                  r["peak_reading_kwh"], int(r["reading_count"])) for r in daily_rows])
            if tariff_rows:
                execute_values(cur, """
                    INSERT INTO tariff_reference (household_id, sim_day, tariff_rate, billing_tier, subsidy_flag)
                    VALUES %s""",
                    [(r["household_id"], sim_day, r["tariff_rate"], r["billing_tier"], bool(r["subsidy_flag"]))
                     for r in tariff_rows])
            execute_values(cur, """
                INSERT INTO daily_billing_report (household_id, sim_day, grid_zone, total_consumption_kwh,
                    total_solar_kwh, net_consumption_kwh, solar_export_kwh, solar_contribution_pct, tariff_rate,
                    billing_tier, subsidy_flag, subsidy_discount_pct, tariff_source, bill_amount, run_id) VALUES %s""",
                [(r["household_id"], sim_day, r["grid_zone"], r["total_consumption_kwh"], r["total_solar_kwh"],
                  r["net_consumption_kwh"], r["solar_export_kwh"], r["solar_contribution_pct"], r["tariff_rate"],
                  r["billing_tier"], bool(r["subsidy_flag"]), r["subsidy_discount_pct"], r["tariff_source"],
                  r["bill_amount"], run_id) for r in bill_rows])

            # Speed vs batch reconciliation for the same day.
            cur.execute("SELECT COALESCE(SUM(consumption_kwh), 0), COALESCE(SUM(reading_count), 0) "
                        "FROM live_household_consumption WHERE sim_day = %s;", (sim_day,))
            speed_kwh, speed_readings = cur.fetchone()
            batch_kwh = sum(r["total_consumption_kwh"] for r in daily_rows)
            batch_readings = sum(int(r["reading_count"]) for r in daily_rows)
            drift_pct = (100.0 * (float(speed_kwh) - batch_kwh) / batch_kwh) if batch_kwh else None
            cur.execute(
                """
                INSERT INTO batch_reconciliation (sim_day, run_id, speed_consumption_kwh, batch_consumption_kwh,
                    drift_pct, speed_readings, batch_readings, raw_events, duplicates_removed, tariff_rows,
                    invalid_tariff_rows, duplicate_tariff_rows, fallback_tariffs, households_billed,
                    households_unbilled, total_billed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sim_day) DO UPDATE SET run_id = EXCLUDED.run_id,
                    speed_consumption_kwh = EXCLUDED.speed_consumption_kwh,
                    batch_consumption_kwh = EXCLUDED.batch_consumption_kwh, drift_pct = EXCLUDED.drift_pct,
                    speed_readings = EXCLUDED.speed_readings, batch_readings = EXCLUDED.batch_readings,
                    raw_events = EXCLUDED.raw_events, duplicates_removed = EXCLUDED.duplicates_removed,
                    tariff_rows = EXCLUDED.tariff_rows, invalid_tariff_rows = EXCLUDED.invalid_tariff_rows,
                    duplicate_tariff_rows = EXCLUDED.duplicate_tariff_rows,
                    fallback_tariffs = EXCLUDED.fallback_tariffs, households_billed = EXCLUDED.households_billed,
                    households_unbilled = EXCLUDED.households_unbilled, total_billed = EXCLUDED.total_billed,
                    reconciled_at = now();
                """,
                (sim_day, run_id, float(speed_kwh), batch_kwh, drift_pct, int(speed_readings), batch_readings,
                 stats["raw_events"], stats["duplicates_removed"], stats["tariff_rows"],
                 stats["invalid_tariff_rows"], stats["duplicate_tariff_rows"], stats["fallback_tariffs"],
                 len(bill_rows), stats["households_unbilled"], round(sum(r["bill_amount"] for r in bill_rows), 2)),
            )
        conn.commit()  # the whole day becomes visible at once
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return drift_pct


def main():
    args = parse_args()
    run_id = uuid.uuid4().hex[:12]  # correlates every log line of this run
    started = time.time()
    spark = SparkSession.builder.appName(f"smart-grid-batch-layer-day{args.sim_day}") \
        .config("spark.sql.session.timeZone", "UTC").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    log_event(logger, "info", "batch_layer_run_started", sim_day=args.sim_day, run_id=run_id,
              tariff_file=args.tariff_file)
    try:
        daily, stats = compute_household_daily(spark, args.sim_day)
        tariff_today, tariff_stats = load_tariff(spark, args.tariff_file, args.sim_day)
        stats.update(tariff_stats)
        bills, unbilled = compute_bills(daily, tariff_today, previous_tariffs(spark, args.sim_day))

        daily_rows, tariff_rows, bill_rows = daily.collect(), tariff_today.collect(), bills.collect()
        stats["fallback_tariffs"] = sum(1 for r in bill_rows if r["tariff_source"] == "fallback_previous_day")
        stats["households_unbilled"] = len(unbilled)
        if unbilled:
            log_event(logger, "warning", "households_without_tariff", sim_day=args.sim_day, run_id=run_id,
                      households=[r["household_id"] for r in unbilled])

        drift_pct = persist_day(args.sim_day, run_id, daily_rows, tariff_rows, bill_rows, stats)
        beat("batch_layer", f"sim_day={args.sim_day} billed={len(bill_rows)} run_id={run_id}", logger=logger)
        log_event(
            logger, "info", "batch_layer_run_complete", sim_day=args.sim_day, run_id=run_id,
            households_billed=len(bill_rows), drift_pct=None if drift_pct is None else round(drift_pct, 3),
            duration_s=round(time.time() - started, 1), **stats,
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "error", "batch_layer_run_failed", sim_day=args.sim_day, run_id=run_id, error=str(exc))
        beat("batch_layer", f"FAILED sim_day={args.sim_day}: {exc}"[:500], status="FAILED", logger=logger)
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
