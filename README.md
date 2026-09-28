Smart Grid Energy Monitoring & Billing — Lambda Architecture Pipeline
EC8203 Applied Big Data Engineering — Mini Project (Use Case 3).

An end-to-end data platform that ingests smart-meter telemetry in real time (Kafka → Spark Structured Streaming) and a daily tariff/billing extract in batch (Airflow → Spark), stores both in a Parquet lake + PostgreSQL, and serves a live dashboard, a REST API and scheduled daily report files that answer:

What is the current grid load and renewable contribution by zone, and what will each household's bill look like once daily tariff data is applied to their consumption?

The full technical report is in report/EC8203_MiniProject_Report.pdf.

Architecture

Architecture: Lambda (and why not Kappa)
Layer	What it does here	Guarantees
Speed	Spark Structured Streaming reads Kafka, validates events, computes 30 s windows (15 s slide, 1 min watermark) of load / solar / renewable % per zone, appends clean events to the Parquet lake, keeps running per-household totals	seconds of latency, approximate (dedup only within a micro-batch, additive totals)
Batch	Airflow runs a Spark job for every finished simulated day: global dedup on event_id, exact household totals from the immutable lake, tariff validation + fallback, join, bill, reconciliation against the speed layer	exact and replayable (idempotent per-day overwrite in one transaction)
Serving	FastAPI merges both views at query time — e.g. /api/billing/projection = speed-layer consumption × batch-validated tariff	
Kappa was rejected because the tariff feed is a once-a-day snapshot, not a stream; billing needs an exact, auditable, cheaply re-runnable daily recomputation (re-read one lake partition instead of replaying the whole Kafka log); and a single stateful streaming job joining a continuous stream with a daily file would be harder to get right and to test. Full argument in the report (section 2).

Tech stack
Layer	Tool	Why (tied to this use case)
Ingestion	Apache Kafka 3.7 (KRaft) — topic smart-meter-readings, 3 partitions, key = household_id	durable, replayable buffer for high-frequency telemetry; keying preserves per-household order while spreading load across partitions; 7-day retention lets the speed layer recover after downtime
Stream processing	Spark Structured Streaming 3.5	event-time windows + watermarks for late data, checkpointed offsets, and the same engine/DataFrame API as the batch job
Orchestration	Apache Airflow 2.9	the daily reconciliation is a dependency chain (wait for file → Spark job → report → alert check) that needs retries, backfill and a UI
Batch source of truth	Parquet data lake, partitioned by sim_day	immutable, columnar, and the batch job reads exactly one partition per day
Serving store	PostgreSQL 16	small, relational outputs queried with filters/joins; upserts + transactions make both layers idempotent
Serving	FastAPI + static dashboard	typed REST API with OpenAPI docs at /docs; the dashboard only uses the public API
Observability	JSON logs, heartbeats, rule engine, Prometheus	see below
Repository layout
config.py                       # single source of configuration (env-var overridable)
common/sim_clock.py             # shared simulated clock (epoch stored in Postgres)
sources/
  smart_meter_producer.py       # streaming source -> Kafka (+ Prometheus metrics :8001)
  tariff_batch_source.py        # daily-batch source -> CSV drop + _SUCCESS marker
processing/
  speed_layer_spark.py          # Structured Streaming: validate, window, lake, running totals
  batch_layer_spark.py          # Spark batch: dedup, exact totals, tariff join, bill, reconcile
  quality_rules.py              # data-quality rules (shared by Spark + tests)
  billing_rules.py              # billing formula (shared by Spark, API + tests)
airflow/dags/daily_batch_pipeline_dag.py
serving/
  api/main.py                   # FastAPI serving layer (speed, batch, merge, observability)
  dashboard/index.html          # live dashboard
  report_generator.py           # scheduled daily CSV + HTML report files
observability/
  logging_config.py             # structured JSON logging
  heartbeat.py                  # component heartbeats -> pipeline_health
  alerts.py                     # alert rule engine
  metrics.py                    # Prometheus metric definitions
  prometheus/                   # prometheus.yml + alert_rules.yml
storage/init.sql                # PostgreSQL schema
scripts/smoke_test.py           # end-to-end check against the running stack
tests/                          # unit tests (no infrastructure needed)
report/                         # report PDF/DOCX, diagrams, screenshots, generators
docker-compose.yml, Dockerfile.app / .spark / .airflow, .env.example
Simulated clock and assumptions
1 simulated day = 300 s (5 min) of real time (SIMULATED_DAY_SECONDS). Day numbering is anchored to one epoch written to Postgres (sim_clock) when the database is created, so every container agrees on sim_day = floor((event_time − epoch) / 300 s). Day fraction 0.5 = noon.
Each of 24 households (4 zones) emits a reading every 2 s. Consumption has morning/evening peaks; solar follows a daylight curve scaled by zone capacity (South has few panels) and daily cloud cover; each day one zone gets an overcast spell (this drives the LOW_RENEWABLE alert).
~1% of events are deliberately dirty (missing field, negative, impossible value, bad timestamp, duplicate); ~1 in 3 tariff files contains an invalid row and some contain a duplicated household. The pipeline must handle them.
The tariff extract for day N is published 20 s after day N ends; the bill for day N is therefore available ~1 min after the day closes.
Billing: bill = max(consumption − solar, 0) × tariff × (1 − 15% if subsidised); no export credit. Renewable contribution = solar ÷ demand (capped at 100%).
Currency is LKR; all data is synthetic.
Running it
Requires Docker Desktop (≈6 GB RAM for Docker) and free ports 8000, 8001, 8080, 9090, 4040, 5433, 29092.

docker compose up --build -d
What	URL
Dashboard	http://localhost:8000/
API docs (OpenAPI)	http://localhost:8000/docs
Airflow UI (admin / admin)	http://localhost:8080 — DAG daily_batch_pipeline is unpaused automatically
Prometheus (targets, alert rules)	http://localhost:9090/alerts
Spark UI (streaming queries)	http://localhost:4040
Producer metrics	http://localhost:8001/
PostgreSQL	localhost:5433, db/user/password smartgrid
Live data appears within ~30 s. The first daily bill appears ~6 minutes after start-up (end of sim-day 0 + 20 s grace + the next DAG poll); report files are written to ./reports/.

Reproducing the results
python scripts/smoke_test.py --wait-billing   # end-to-end checks, exits 0 on success
docker compose logs -f spark-speed-layer      # JSON logs of every micro-batch
docker compose exec postgres psql -U smartgrid -c "SELECT * FROM batch_reconciliation ORDER BY sim_day;"
Failure drills (observability demo)
docker compose stop meter-producer   # -> NO_DATA alerts for producer + speed layer within ~2 min, /health DEGRADED
docker compose start meter-producer  # -> alerts auto-resolve
Tests
pip install -r requirements.txt
pytest tests -v        # 44 unit tests, no Docker needed
Tear down
docker compose down        # keep data
docker compose down -v     # also delete Kafka / Postgres / lake volumes (fresh sim clock)
Observability
Structured logging — every stage logs one JSON object per event to stdout and ./logs/<component>.log, with correlation fields (sim_day, batch_id, run_id, event_id, household_id).
Metrics — GET /metrics (API) exports component staleness, per-zone renewable % and load, stream volume / invalid rate / lag, reconciliation drift, open alerts by type, request counts/latency. The producer exports delivery counters on :8001. Prometheus scrapes both.
Health — GET /health: per-component heartbeat freshness against a per-component budget (the batch layer is allowed to be silent for a day).
Alert rules — observability/alerts.py (runs every 15 s and after each batch run) + the equivalent Prometheus rules in observability/prometheus/alert_rules.yml:
Rule	Condition
LOW_RENEWABLE	zone renewable % < 10% during simulated daylight
NO_DATA	component heartbeat older than its budget (2 min for streaming components)
COMPONENT_FAILED	component reported a failure (e.g. batch job exception)
HIGH_INVALID_RATE	> 5% of events quarantined in the last 5 min
HIGH_STREAM_LAG	event-time → sink lag > 60 s
RECONCILIATION_DRIFT	speed vs batch daily consumption differ by > 10%
PIPELINE_TASK_FAILED	an Airflow task failed (on_failure_callback)
Alerts are de-duplicated (one open alert per type+scope), auto-resolve when the condition clears, and can be pushed to a Slack/Teams webhook via ALERT_WEBHOOK_URL.

Limitations
Single-broker Kafka (RF=1), Spark in local[2] mode, Airflow standalone (SequentialExecutor + SQLite), a Docker-volume data lake instead of S3/HDFS, at-least-once delivery (duplicates are removed in the batch layer, not the speed layer), no authentication on the API/dashboard. See the report, section 9, for the production-scale changes.
