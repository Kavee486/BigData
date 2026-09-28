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
