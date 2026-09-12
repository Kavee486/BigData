# Smart Grid Energy Monitoring & Billing — Lambda Architecture Pipeline

EC8203 Applied Big Data Engineering — Mini Project.

An end-to-end data platform that ingests smart-meter telemetry in real time
and daily tariff/billing reference files in batch, then answers:

> **What is the current grid load and renewable contribution by zone, and
> what will each household's bill look like once daily tariff data is
> applied to their consumption?**

## Architecture: Lambda

We use a **Lambda architecture**: a speed layer gives an approximate,
low-latency real-time view of grid load/renewable mix; a batch layer
recomputes an accurate daily view from the immutable raw event log and joins
it with the tariff feed to produce bills. Both views are merged at query
time by the serving API. Full justification (vs. Kappa) is in `report/`.

```
                       ┌──────────────────────┐
 smart_meter_producer  │        Kafka          │
   (streaming source) ─▶  smart-meter-readings │
                       └──────────┬────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
         SPEED LAYER (Spark Structured    Raw event archive
         Streaming, windowed agg by       (Parquet data lake,
         grid_zone) ── every ~10s              partitioned by
                    │                           sim_day)
                    ▼                                │
          Postgres: live_zone_metrics                │
                    │                                ▼
                    │                    BATCH LAYER (Spark batch,
 tariff_batch_source│                    Airflow-orchestrated once
 (daily-batch       │                    per simulated day):
  source) ──────────┼──▶ tariff CSV ──▶  recompute household daily
                    │    drop             totals + join tariff
                    │                     ──▶ daily_billing_report
                    ▼                                │
        ┌───────────────────────────────────────────┘
        ▼
  Postgres (serving DB): live_zone_metrics, alerts,
  household_daily_consumption, tariff_reference,
  daily_billing_report, pipeline_health
        │
        ▼
  FastAPI serving layer  ──▶  Dashboard (static HTML/JS)
  /api/grid/live, /api/alerts, /api/billing/daily, /health, /metrics
```

## Tech stack & why

| Layer | Tool | Why (tied to this use case) |
|---|---|---|
| Ingestion | **Apache Kafka** | Durable, replayable buffer for high-frequency meter telemetry; partitioned so per-zone/per-household ordering and parallel consumption both work; the raw log Kafka retains is also what makes recomputation (batch layer) possible. |
| Stream processing | **Spark Structured Streaming** | Native windowed aggregation over Kafka with watermarking, same Spark API reused for the batch job (one processing engine, less operational surface, easy to reason about consistency between speed/batch views). |
| Orchestration | **Apache Airflow** | Daily tariff reconciliation is a classic scheduled DAG with a clear dependency chain (wait for file → join → alert-check → notify); retries/backfill/observability of the *batch* pipeline come for free. |
| Storage/serving | **PostgreSQL** | All outputs (zone metrics, alerts, billing) are small, relational, and need to be queried with filters/joins by the API — Postgres is the simplest correct fit; no need for Cassandra's write-heavy wide-column model or HDFS's file-oriented access here. |
| Data lake (batch source of truth) | **Parquet on local volume** | Cheap immutable, columnar archive of raw events that the batch layer re-reads to compute the accurate view — the defining requirement of Lambda's batch layer. |
| Serving | **FastAPI** | Thin, fast, typed REST layer over Postgres; merges speed + batch views at query time. |
| Observability | **JSON structured logging + Prometheus metrics + custom alert rules** | Every stage logs uniformly parseable events; `/metrics` exposes counters/gauges; a lightweight rule engine flags low-renewable zones and stalled components. |

## Repository layout

```
config.py                     # single source of config, env-var overridable
sources/                      # simulated data sources
  smart_meter_producer.py     #   streaming: Kafka producer
  tariff_batch_source.py      #   daily-batch: CSV drop
processing/
  speed_layer_spark.py        # Structured Streaming: windowed agg + raw archive
  batch_layer_spark.py        # batch: recompute + join + bill
  billing_rules.py            # pure billing formula (unit-tested)
airflow/dags/
  daily_batch_pipeline_dag.py # orchestrates the batch layer once/sim-day
serving/
  api/main.py                 # FastAPI: live view, alerts, billing, health, metrics
  dashboard/index.html         # static live dashboard
observability/
  logging_config.py           # shared JSON logger
  alerts.py                    # threshold + no-data alert engine
  metrics.py                   # Prometheus registry
storage/init.sql               # Postgres schema
tests/                         # pure-Python unit tests (no infra required)
docker-compose.yml
Dockerfile.app / .spark / .airflow
```

## Simulated clock

`SIMULATED_DAY_SECONDS=300` by default — **1 simulated day = 5 minutes of
real time**. The batch source drops one tariff file every simulated day; the
Airflow DAG is scheduled on the same interval so a full day/batch cycle can
be observed within a single short demo session. Meter readings are emitted
every `METER_EMIT_INTERVAL_SECONDS=2` seconds per household. Both are
configurable via environment variables in `docker-compose.yml`.

## Running it

Requires Docker Desktop.

```bash
docker compose up --build
```

This starts, in dependency order: Zookeeper, Kafka, Postgres (auto-applies
`storage/init.sql`), the two simulated sources, the Spark speed-layer
streaming job, the alerts engine, the FastAPI serving layer, and Airflow
(standalone mode, SequentialExecutor — a mini-project simplification; see
Limitations).

- **Dashboard**: http://localhost:8000/
- **API docs**: http://localhost:8000/docs
- **Airflow UI**: http://localhost:8080 (user `admin` / password `admin`) — enable the `daily_batch_pipeline` DAG.
- **Metrics**: http://localhost:8000/metrics

Wait ~30-60s after `up` for Kafka to become healthy before the producer and
speed layer connect (they retry automatically — see their logs).

### Watching it work end to end

```bash
docker compose logs -f meter-producer spark-speed-layer
```

Within a few seconds you should see `live_zone_metrics` populate — refresh
the dashboard to see live load/renewable % per zone. After one simulated day
(default 5 minutes), `tariff-batch-source` drops a CSV, the Airflow DAG's
sensor picks it up, runs the batch Spark job, and the dashboard's "Latest
Daily Billing Report" table populates.

### Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

(The included tests are infra-free — they exercise the simulators' value
ranges and the billing arithmetic directly, so they run without Docker.)

## Observability

- **Structured logging**: every component (`sources/*`, `processing/*`,
  `serving/api`, `observability/alerts.py`) logs JSON lines via
  `observability/logging_config.py` to stdout and `/logs/<component>.log`.
- **Metrics**: `GET /metrics` (Prometheus text format) exposes request
  counts, active alert count, per-zone renewable %, and per-component
  pipeline staleness.
- **Health check**: `GET /health` reports `OK`/`DEGRADED` per component
  based on `pipeline_health.last_heartbeat` freshness.
- **Alert rules** (`observability/alerts.py`, also run once per Airflow DAG
  run): `LOW_RENEWABLE` (a zone's renewable contribution drops below
  `LOW_RENEWABLE_PCT_THRESHOLD`) and `NO_DATA` (a component hasn't
  heartbeat in `NO_DATA_ALERT_MINUTES`). Alerts are deduplicated with a
  60s cooldown and served at `GET /api/alerts`.

## Limitations & what's simplified

See `report/` for the full discussion; in short: Airflow runs in
single-node SequentialExecutor/SQLite mode (fine for this demo scale, not
production-grade); the data lake is a local Docker volume rather than
HDFS/S3; there's no exactly-once end-to-end guarantee (at-least-once via
Kafka + idempotent upserts is used instead); and the alert engine is a
polling loop rather than a dedicated monitoring stack (Prometheus/Grafana).

## Individual contributions

_(Fill in if submitted as a group: name — components owned.)_
