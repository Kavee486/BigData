// Generates report/EC8203_MiniProject_Report.docx from the text below plus the
// evidence captured from a real run (report/results/*.json, report/screenshots/*.png,
// produced by report/capture_results.py). Run from the repo root:
//     node report/gen_report.js
// then export to PDF (report/export_pdf.ps1 uses Microsoft Word).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, ImageRun, PageBreak, TableOfContents, Header, Footer, PageNumber,
} = require("docx");

const FONT = "Calibri";
const NAVY = "1F3B57";
const ACCENT = "2F6FED";
const R = (f) => path.join("report", f);
const J = (name) => JSON.parse(fs.readFileSync(R(`results/${name}.json`), "utf8"));

// ---------------------------------------------------------------- helpers
const h1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1, pageBreakBefore: false });
const h2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2 });
function runs(text, base = {}) {
  // **bold** and `code` inline markup
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).filter(Boolean).map((t) => {
    if (t.startsWith("**")) return new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, size: 21, ...base });
    if (t.startsWith("`")) return new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 19, color: "0B4F8A", ...base });
    return new TextRun({ text: t, font: FONT, size: 21, ...base });
  });
}
const p = (text, opts = {}) => new Paragraph({ spacing: { after: 140, line: 276 }, alignment: AlignmentType.JUSTIFIED, children: runs(text), ...opts });
const bullet = (text, level = 0) => new Paragraph({ spacing: { after: 70, line: 264 }, bullet: { level }, children: runs(text) });
const pb = () => new Paragraph({ children: [new PageBreak()] });

function cell(text, { header = false, width, shade } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    children: [new Paragraph({ children: runs(String(text), { size: 18, bold: header || undefined, color: header ? "FFFFFF" : undefined }) })],
  });
}
function table(headerRow, rows, widths) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headerRow.map((t, i) => cell(t, { header: true, width: widths[i], shade: NAVY })) }),
      ...rows.map((r, ri) => new TableRow({ children: r.map((t, i) => cell(t, { width: widths[i], shade: ri % 2 ? "F2F5FA" : "FFFFFF" })) })),
    ],
  });
}
const spacer = () => new Paragraph({ spacing: { after: 80 }, children: [] });

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
let figNo = 0;
function figure(file, caption, widthIn = 6.5, maxHeightIn = 8.2) {
  const full = R(file);
  if (!fs.existsSync(full)) return [p(`[missing figure: ${file}]`)];
  const { w, h } = pngSize(full);
  let width = widthIn, height = (widthIn * h) / w;
  if (height > maxHeightIn) { height = maxHeightIn; width = (maxHeightIn * w) / h; }
  figNo += 1;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: Math.round(width * 96), height: Math.round(height * 96) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 220 },
      children: [new TextRun({ text: `Figure ${figNo}. ${caption}`, italics: true, size: 18, color: "555555", font: FONT })] }),
  ];
}
function code(text) {
  return new Paragraph({
    spacing: { after: 160 }, shading: { type: ShadingType.CLEAR, fill: "F3F4F6" },
    children: text.split("\n").flatMap((line, i) => [new TextRun({ text: line, font: "Consolas", size: 16, break: i ? 1 : 0 })]),
  });
}
const f2 = (v, d = 2) => (v === null || v === undefined ? "–" : Number(v).toFixed(d));
const money = (v) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------------------------------------------------------------- evidence
const recon = J("reconciliation").rows.slice().sort((a, b) => a.sim_day - b.sim_day);
const billing = J("billing_daily");
const summary = J("billing_summary");
const live = J("grid_live");
const status = J("pipeline_status");
const alertsOpen = J("alerts_open").alerts;
const alertsResolved = J("alerts_resolved").alerts;
const projection = J("billing_projection");
const drill = fs.existsSync(R("results/failure_drill.json")) ? J("failure_drill") : null;
const tests = fs.existsSync(R("results/pytest.txt")) ? fs.readFileSync(R("results/pytest.txt"), "utf8").trim() : "";
const smoke = fs.existsSync(R("results/smoke_test.txt")) ? fs.readFileSync(R("results/smoke_test.txt"), "utf8").trim() : "";
const totalRaw = recon.reduce((a, r) => a + r.raw_events, 0);
const totalDup = recon.reduce((a, r) => a + r.duplicates_removed, 0);
const alertCounts = {};
for (const a of [...alertsOpen, ...alertsResolved]) alertCounts[a.alert_type] = (alertCounts[a.alert_type] || 0) + 1;

const S = [];

// ================================================================= TITLE
S.push(
  new Paragraph({ spacing: { before: 1800 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Smart Grid Energy Monitoring & Billing", bold: true, size: 48, font: FONT, color: NAVY })] }),
  new Paragraph({ spacing: { before: 160 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "An End-to-End Lambda-Architecture Data Pipeline", size: 30, font: FONT, color: ACCENT })] }),
  new Paragraph({ spacing: { before: 500 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "EC8203 Applied Big Data Engineering — Mini Project Report", size: 24, font: FONT })] }),
  new Paragraph({ spacing: { before: 120 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Use Case 3: Smart Grid Energy Monitoring & Billing", size: 22, italics: true, font: FONT })] }),
  new Paragraph({ spacing: { before: 900 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Name: ______________________________", size: 22, font: FONT })] }),
  new Paragraph({ spacing: { before: 160 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Registration No.: ____________________", size: 22, font: FONT })] }),
  new Paragraph({ spacing: { before: 160 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Repository: smart-grid-pipeline/ (docker compose up --build -d)", size: 20, font: FONT, color: "555555" })] }),
  new Paragraph({ spacing: { before: 900 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "September 2026", size: 20, font: FONT, color: "666666" })] }),
  pb(),
  new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 28, color: NAVY, font: FONT })] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  pb(),
);

// ================================================================= 1
S.push(h1("1. Use Case and Business Requirements"));
S.push(p("A utility company wants real-time visibility into grid load and the renewable (solar) contribution from household smart meters, reconciled once a day against tariff and billing reference data published by its billing system. We implemented **Use Case 3** with both required source types: a continuous smart-meter stream and a once-per-day tariff extract."));
S.push(h2("1.1 Business question and derived requirements"));
S.push(p("**Business question:** “What is the current grid load and renewable contribution by zone, and what will each household's bill look like once daily tariff data is applied to their consumption?” We decomposed it into functional (FR) and non-functional (NFR) requirements, which drive every later decision:"));
S.push(table(["ID", "Requirement", "Where it is met"], [
  ["FR1", "Live load, solar generation and renewable % per grid zone", "Speed layer → `/api/grid/live`, dashboard"],
  ["FR2", "Alert when renewable contribution is considerably low", "`LOW_RENEWABLE` rule (daylight only)"],
  ["FR3", "Daily per-household bill and solar-contribution report once the tariff arrives", "Batch layer → `daily_billing_report`, CSV/HTML report files"],
  ["FR4", "An estimate of today's bill before the day closes", "Lambda merge → `/api/billing/projection`"],
  ["FR5", "Tolerate dirty data in both feeds", "Quarantine, dedup, tariff validation + fallback"],
  ["NFR1 Latency", "Live view within seconds; bills within minutes of the tariff file", "10 s micro-batches; DAG polls every 60 s"],
  ["NFR2 Correctness / replay", "Bills must be exact, reproducible and re-runnable", "Immutable Parquet lake + idempotent per-day overwrite"],
  ["NFR3 Consistency", "Readers never see half a day; speed and batch comparable", "Single-transaction day write; reconciliation table"],
  ["NFR4 Observability", "Detect and diagnose failures in any stage", "JSON logs, heartbeats, 7 alert rules, Prometheus"],
  ["NFR5 Cost / operability", "Runs on one laptop with one command", "Docker Compose, 9 containers"],
], [1150, 4700, 4000]));
S.push(spacer());
S.push(h2("1.2 Data sources (simulated, Python)"));
S.push(p("**Streaming source** (`sources/smart_meter_producer.py`): 24 households in 4 zones each emit a JSON reading every 2 s — `event_id, meter_id, household_id, power_consumption_kwh, solar_generation_kwh, grid_zone, timestamp`. Consumption follows morning/evening peaks with noise and ~1% demand spikes; solar follows a daylight curve scaled by zone capacity (South has few panels) and a deterministic daily cloud factor, and each simulated day one zone suffers an overcast spell. ~1% of events are deliberately dirty (missing field, negative or impossible value, unparsable timestamp, or an exact duplicate simulating at-least-once redelivery)."));
S.push(p("**Daily-batch source** (`sources/tariff_batch_source.py`): 20 s after each simulated day ends it publishes that day's end-of-day extract `tariff_simdayN.csv` (`household_id, tariff_rate, billing_tier, subsidy_flag, sim_day, published_at`). The file is written to a temporary name, atomically renamed, and only then is a `_SUCCESS_simdayN` marker written. Tier and subsidy are fixed per household and the daily rate drift is seeded by (household, day), so regenerating a day yields an identical file. About one file in three contains an invalid rate and some contain a duplicated household row; on restart the source back-fills any missing days."));
S.push(h2("1.3 Simulated clock and assumptions"));
S.push(bullet("**1 simulated day = 300 s of real time** (`SIMULATED_DAY_SECONDS`, configurable). Day fraction 0.5 is simulated noon; daylight for alerting is fraction 0.40–0.60."));
S.push(bullet("Day numbers come from ONE epoch stored in Postgres (`sim_clock`) when the database is created: `sim_day = floor((event_time − epoch) / 300)`. Using event time (not processing time) means a late event is still attributed to the correct day and every container agrees on day boundaries."));
S.push(bullet("Billing: `bill = max(consumption − solar, 0) × tariff_rate × (1 − 15% if subsidised)`; no export credit. Renewable contribution = solar ÷ demand, capped at 100%. Currency LKR. All data is synthetic."));

// ================================================================= 2
S.push(h1("2. Architecture Decision: Lambda vs Kappa"));
S.push(p("Both architectures ingest the same immutable event log. **Kappa** has one stream-processing code path and recomputes history by replaying the log through it. **Lambda** keeps a speed layer for low-latency, approximate results and a batch layer that periodically recomputes exact results from the master dataset, with the serving layer merging both. We evaluated them against the four dimensions the rubric names:"));
S.push(table(["Dimension", "What this use case needs", "Lambda", "Kappa"], [
  ["Latency", "Seconds for the grid view; minutes for bills", "Speed layer: ~10–15 s end-to-end (measured). Batch: bill ~1 min after the tariff file", "Same stream latency; bills also streaming"],
  ["Replay / correction", "Re-bill one day after a corrected tariff file or a code fix", "Re-run one Spark job over one Parquet partition (`sim_day=N`), idempotent", "Replay the retained Kafka log from before day N through a new job version, then swap outputs"],
  ["Consistency", "Exact, auditable, all-or-nothing daily bills; duplicates removed", "Global dedup on `event_id` + single-transaction day overwrite", "Needs exactly-once state + careful watermarking to finalise a day"],
  ["Cost / complexity", "Laptop-scale, 2-week build, defendable line by line", "Two code paths (mitigated: one engine, shared rule modules)", "One code path, but a long-state stream-to-file join"],
], [1400, 2600, 2950, 2900]));
S.push(spacer());
S.push(h2("2.1 Why Lambda fits this problem"));
S.push(bullet("**The sources have different natures.** Meter readings are a true stream; the tariff feed is a complete once-a-day snapshot. Lambda lets each be processed in its natural form. In Kappa, the daily file would have to be pushed into Kafka as a degenerate 24-event stream and joined against the meter stream with day-long state and a watermark long enough to cover a file that arrives after the day ends."));
S.push(bullet("**Billing is correctness-critical and must be replayable.** A bill must be reproducible from source data. Our batch layer recomputes each household's total from the immutable lake with a global dedup on `event_id` and replaces the day's rows in one transaction; re-running it for the same day gives identical bills. The speed layer is explicitly allowed to be approximate — it only dedups within a micro-batch and keeps additive running totals, which double-count if Kafka redelivers after a crash."));
S.push(bullet(`**We can measure the difference, not just claim it.** For every billed day the batch job writes speed-vs-batch drift to \`batch_reconciliation\`. Across the ${recon.length} simulated days of our run, drift ranged from ${f2(Math.min(...recon.map(r => r.drift_pct)))}% to ${f2(Math.max(...recon.map(r => r.drift_pct)))}% and the batch layer removed ${totalDup} duplicate events that the speed layer had counted (section 8).`));
S.push(bullet("**Cheap, scoped reprocessing.** Correcting day N means re-reading one small partition, not the whole log; the raw lake also outlives Kafka's 7-day retention, which a Kappa design would need to extend indefinitely (or add tiered storage) to reprocess older days."));
S.push(bullet("**Orchestration has a natural home.** The batch layer is a dependency chain (wait for file → Spark → report → re-check alerts) that benefits from Airflow's retries, backfill and UI."));
S.push(h2("2.2 The rejected alternative: Kappa"));
S.push(p("Kappa would win if **all** inputs were naturally streams, if bills were needed continuously rather than per day, or if keeping two code paths consistent were the dominant cost. Its genuine advantages are one code path, no batch/speed divergence by construction, and simpler operations. We rejected it here because (1) the daily tariff snapshot is not a natural stream, (2) finalising a day exactly in a stream requires exactly-once state and a watermark tuned to a file that arrives after the day ends, and (3) correcting one day would mean replaying the log through a new job version and swapping outputs — disproportionate for a one-day fix. We keep the replayable Kafka log anyway, so a future move towards Kappa is possible."));
S.push(...figure("lambda_vs_kappa.png", "Lambda (chosen) versus Kappa (rejected) for this use case.", 6.3));
S.push(h2("2.3 Trade-offs we accepted and how we contain them"));
S.push(bullet("**Two code paths that could diverge.** Mitigated by using Spark for both layers and by sharing the rules: `processing/quality_rules.py` (validation) and `processing/billing_rules.py` (the bill formula, used by the batch job and by the API's projection). The end-to-end smoke test re-checks every produced bill against `compute_bill()`."));
S.push(bullet("**The speed view can be briefly wrong** (duplicates, late events beyond the 1-minute watermark). Accepted because it is only used for monitoring and provisional estimates, which the API labels `provisional`; final bills come from the batch layer only."));
S.push(bullet("**Bills are only available after the day closes (plus ~1 min).** Accepted: the business asks for daily bills, and `/api/billing/projection` covers the intra-day need."));

// ================================================================= 3
S.push(h1("3. System Architecture"));
S.push(...figure("architecture_diagram.png", "End-to-end architecture across the ingestion, processing, storage and serving layers, with observability as a cross-cutting concern.", 6.6));
S.push(p("**Data flow.** (1) The producer writes readings to Kafka topic `smart-meter-readings` (3 partitions, keyed by `household_id`). (2) The speed layer runs two Structured Streaming queries from checkpointed offsets: a windowed aggregate per zone that is upserted into `live_zone_metrics`, and a `foreachBatch` sink that quarantines invalid events, appends clean events to the Parquet lake partitioned by `sim_day`, adds per-household running totals and records data-quality/lag metrics. (3) After day N ends, the tariff source drops its CSV and `_SUCCESS` marker. (4) The Airflow DAG detects the oldest unbilled finished day, waits for the marker, runs the Spark batch job and publishes report files. (5) The batch job writes the whole day to PostgreSQL in one transaction. (6) FastAPI serves the speed view, the batch view and their merge; the dashboard, the report files and Prometheus consume it."));

// ================================================================= 4
S.push(h1("4. Technology Stack and Justification"));
S.push(table(["Layer", "Choice", "Why this fits the use case", "Alternatives considered"], [
  ["Ingestion", "Apache Kafka 3.7 (KRaft, 1 broker), 3 partitions, key = household_id, acks=all, 7-day retention", "Durable, replayable buffer for continuous telemetry; keying keeps each household's readings ordered while spreading 24 meters across partitions for parallel consumers; retention lets the speed layer catch up after an outage (it starts from checkpointed offsets)", "RabbitMQ (no replay/offsets); Kafka+ZooKeeper (KRaft removes a component)"],
  ["Stream processing", "Spark Structured Streaming 3.5", "Event-time windows with watermarks for late meter data, checkpointed exactly-once source offsets, micro-batch `foreachBatch` for multi-sink writes, and the same DataFrame API as the batch job — one engine to learn and defend", "Apache Storm (tuple-at-a-time, no shared batch API); Flink (not in the preferred stack; lower latency we do not need)"],
  ["Batch processing", "Spark (local[2]) via spark-submit", "Scans one Parquet partition per day, global dedup, joins with the tariff file; scales to a cluster unchanged", "Plain pandas (would not scale; different API from the speed layer)"],
  ["Orchestration", "Apache Airflow 2.9", "Daily dependency chain with a file sensor, retries, failure callbacks, backfill (look-back of 3 days) and a UI for demo/diagnosis", "Cron (no dependencies, retries or visibility)"],
  ["Master dataset", "Parquet data lake partitioned by `sim_day`", "Immutable, columnar, cheap; partition pruning means a day's recompute reads only that day", "Keeping raw events in Postgres (row store, grows unbounded)"],
  ["Serving store", "PostgreSQL 16", "Outputs are small and relational and are queried with filters, joins (projection = live totals × latest tariff) and aggregates; transactions and upserts make both layers idempotent", "Cassandra (write-optimised, no joins/transactions — our reads need both); HDFS/S3 alone (not a low-latency query store)"],
  ["Serving API / UI", "FastAPI + static HTML dashboard", "Typed endpoints and generated OpenAPI docs; dashboard uses only the public API", "Grafana-only (cannot express the billing merge)"],
  ["Observability", "JSON logging, Postgres heartbeats, Python rule engine, Prometheus", "Business- and pipeline-aware rules (daylight-aware renewable rule, per-component staleness budgets) plus a standard metrics/alerting stack", "ELK/Grafana (heavier than needed for one machine)"],
  ["Packaging", "Docker Compose (9 services)", "One-command reproducible environment; images built from official bases (apache/kafka, apache/airflow, python + pyspark wheel)", "Manual installs"],
], [1250, 2250, 4050, 2300]));

// ================================================================= 5
S.push(h1("5. Implementation"));
S.push(h2("5.1 Ingestion"));
S.push(bullet("The producer creates the topic explicitly with `KafkaAdminClient` (3 partitions), retries while the broker starts, uses `acks=all`, `max_in_flight_requests_per_connection=1` (ordering on retry) and delivery callbacks that count acknowledged/failed sends; it flushes and closes cleanly on SIGTERM and exposes Prometheus counters on port 8001."));
S.push(bullet("The batch source never exposes a partial file (temp file + atomic rename + marker written last), is deterministic for replays, and back-fills missed days after a restart."));
S.push(h2("5.2 Speed layer (processing/speed_layer_spark.py)"));
S.push(bullet("Reads Kafka from `earliest` on first start and from checkpointed offsets afterwards (checkpoints live on the lake volume), so nothing produced before Spark is ready is lost and restarts resume where they stopped."));
S.push(bullet("**Cleaning:** every event is parsed against an explicit schema and validated by the same rules as `quality_rules.py` (missing field, bad timestamp, unknown zone, negative, above 50 kWh). Invalid events are written with their reason to a quarantine Parquet path — never silently dropped."));
S.push(bullet("**Windowing and aggregation:** clean events → 1-minute watermark → 30 s windows sliding every 15 s per zone → load, solar, renewable % and distinct households → idempotent upsert into `live_zone_metrics` (update output mode)."));
S.push(bullet("**Master dataset and enrichment:** in the second query each micro-batch is deduplicated on `event_id`, tagged with its event-time `sim_day` and appended to `raw_meter_events/sim_day=N`; per-household running totals for the day are added into `live_household_consumption`; volume, invalid counts by reason, duplicates and event-to-sink lag go to `stream_quality_metrics`, and a heartbeat to `pipeline_health`."));
S.push(h2("5.3 Batch layer (processing/batch_layer_spark.py) and orchestration"));
S.push(bullet("Reads only partition `sim_day=N`, removes duplicates **globally** on `event_id`, and computes exact totals: consumption, solar, net, solar export, solar-contribution %, peak reading and reading count per household."));
S.push(bullet("Reads the tariff CSV with an explicit all-string schema, rejects rows with blank, non-numeric or non-positive rates or unknown tiers, keeps one row per household, and **falls back to the household's last valid tariff** from earlier days (flagged `tariff_source = fallback_previous_day`). Households with no tariff at all are logged and counted, not billed with a guess."));
S.push(bullet("Joins consumption with tariffs, applies the billing formula and writes `household_daily_consumption`, `tariff_reference`, `daily_billing_report` and `batch_reconciliation` with delete-then-insert for day N **in one transaction** — the day appears atomically and re-runs are idempotent. Each run has a `run_id` that appears in every log line and in the bills."));
S.push(bullet("The Airflow DAG `daily_batch_pipeline` runs every 60 s: `resolve_sim_day` (ShortCircuit: oldest finished, unbilled day with raw data, 3-day look-back) → `wait_for_tariff_file` (sensor) → `run_batch_layer` (spark-submit) → `publish_report` (CSV + HTML) → `run_alert_check` → `notify_complete`. Retries (2 × 20 s) and an `on_failure_callback` that raises a CRITICAL `PIPELINE_TASK_FAILED` alert make failures visible. Polling + ShortCircuit is used instead of a daily cron because with the compressed clock days end every 5 minutes at arbitrary offsets."));
S.push(...figure("screenshots/airflow_grid.png", "Airflow grid view of daily_batch_pipeline: full runs (green) bill a finished simulated day; polls in between short-circuit and skip downstream tasks (pink).", 6.5));
S.push(h2("5.4 Storage and serving layer"));
S.push(table(["Table / path", "Written by", "Purpose"], [
  ["Parquet `raw_meter_events/sim_day=N`", "Speed layer", "Immutable master dataset for the batch layer"],
  ["Parquet `quarantine_meter_events/invalid_reason=…`", "Speed layer", "Rejected events kept for diagnosis"],
  ["`live_zone_metrics`", "Speed layer", "Windowed load / solar / renewable % per zone (6 h retention)"],
  ["`live_household_consumption`", "Speed layer", "Approximate running totals for the current day"],
  ["`stream_quality_metrics`", "Speed layer", "Per micro-batch volume, invalid/duplicate counts, lag"],
  ["`household_daily_consumption`, `tariff_reference`, `daily_billing_report`", "Batch layer", "Exact daily view and bills"],
  ["`batch_reconciliation`", "Batch layer", "Speed vs batch drift and data-quality counters per day"],
  ["`alerts`, `pipeline_health`, `sim_clock`", "Observability / shared", "Alert lifecycle, heartbeats, shared epoch"],
], [3700, 1700, 4450]));
S.push(spacer());
S.push(table(["Endpoint", "View", "Answers"], [
  ["`GET /api/grid/live`, `/api/grid/history`", "Speed", "Current load, solar and renewable % per zone; 15-minute history"],
  ["`GET /api/households/live`", "Speed", "Today's running consumption per household"],
  ["`GET /api/billing/daily`, `/summary`, `/days`", "Batch", "Per-household bill and solar contribution; zone roll-up; billed days"],
  ["`GET /api/billing/projection`", "**Merge**", "Provisional bill so far today = speed consumption × latest batch-validated tariff, beside the last final bill"],
  ["`GET /api/reconciliation`", "Batch", "Speed-vs-batch drift and data-quality counters"],
  ["`GET /api/alerts`, `/api/pipeline/status`, `/health`, `/metrics`", "Observability", "Open/resolved alerts, heartbeats, stream quality, Prometheus metrics"],
], [3900, 1200, 4750]));
S.push(spacer());
S.push(p("The latest-window query deliberately returns the latest **complete** window per zone (a still-open window holds only a few seconds of data and would under-report load). Database outages are turned into logged HTTP 503 responses rather than crashes. The API also serves the dashboard and generated OpenAPI docs."));

// ================================================================= 6
S.push(h1("6. Observability Design"));
S.push(p("The goal is that any failure — a dead producer, a stuck Spark query, a crashed batch job, a bad input file — is **detected** automatically and can be **diagnosed** from a single place. We instrument four signal types:"));
S.push(table(["Signal", "How it is produced", "Why"], [
  ["Structured logs", "Every component logs one JSON object per event (`time, level, component, msg` + fields) to stdout and `logs/<component>.log`; correlation keys `sim_day`, `batch_id`, `run_id`, `event_id`, `household_id`", "Trace one day or one batch run across producer → Spark → Airflow → API; machine-parseable for a log shipper"],
  ["Heartbeats", "Each long-running component upserts `pipeline_health` (status + detail); each component has its own staleness budget", "Liveness per stage; the batch layer is legitimately silent for a day, so one global threshold would give false alarms"],
  ["Pipeline metrics", "`stream_quality_metrics` per micro-batch; `batch_reconciliation` per day; exported by `/metrics` (refreshed from Postgres on each scrape) and the producer's `:8001`", "Volume, invalid rate by reason, duplicates, event-time lag, speed-vs-batch drift, delivery failures, request latency"],
  ["Alerts", "Rule engine `observability/alerts.py` every 15 s and after each batch run; Prometheus evaluates the equivalent `alert_rules.yml`", "Turns signals into de-duplicated, auto-resolving, optionally webhook-notified alerts"],
], [1500, 4600, 3750]));
S.push(spacer());
S.push(table(["Rule", "Condition (default threshold)", "Detects"], [
  ["LOW_RENEWABLE (business)", "zone renewable % < 10% in the latest complete window, during simulated daylight only", "Grid leaning on non-renewable supply (e.g. overcast zone)"],
  ["NO_DATA", "heartbeat older than the component's budget (2 min streaming; 2 days + 2 min for the batch layer)", "Dead/stuck producer, Spark query, alerts engine or batch layer"],
  ["COMPONENT_FAILED", "component reported status ≠ OK (e.g. batch job exception)", "Crashes that still heartbeat"],
  ["HIGH_INVALID_RATE", "> 5% of events quarantined in 5 min", "Upstream schema/sensor problem"],
  ["HIGH_STREAM_LAG", "average event→sink lag > 60 s", "Speed layer falling behind"],
  ["RECONCILIATION_DRIFT", "|speed − batch| / batch > 10% for the last billed day", "Speed-layer double counting / data loss"],
  ["PIPELINE_TASK_FAILED", "Airflow `on_failure_callback`", "Batch orchestration failure"],
], [2300, 4300, 3250]));
S.push(p("Alerts are stored with a partial unique index so that at most one alert per (type, scope) is open; while the condition persists its `last_seen_at` and value are refreshed, and when it clears the alert is auto-resolved. Every transition is logged, and posted to a Slack/Teams-compatible webhook when `ALERT_WEBHOOK_URL` is set."));
if (drill) {
  S.push(h2("6.1 Failure drill: stopping the streaming source"));
  S.push(p(`To show that failures are detected and diagnosable, we stopped the producer container (\`docker compose stop meter-producer\`) at ${drill.stopped_at} UTC. ${drill.summary}`));
  S.push(table(["Time (UTC)", "Observation"], drill.timeline.map((t) => [t.time, t.what]), [1800, 8050]));
  S.push(spacer());
  if (fs.existsSync(R("screenshots/drill_dashboard.png"))) S.push(...figure("screenshots/drill_dashboard.png", "Dashboard during the drill: NO_DATA alerts and stale components.", 6.4));
}

// ================================================================= 7
S.push(h1("7. Testing and Reproducibility"));
S.push(bullet("**Unit tests** (`tests/`, no infrastructure): data-quality rules, billing formula, simulated clock, both simulators (fields, value ranges, determinism, overcast spell, every dirty kind fails validation, atomic file drop), alert predicates, API endpoints with a stubbed database (projection merge, health staleness, DB-outage 503, metrics) and the report renderer."));
if (tests) S.push(code(tests));
S.push(bullet("**End-to-end smoke test** (`scripts/smoke_test.py`) against the running stack: events delivered, live windows for all zones, quarantine working, `/health` OK, Prometheus rules loaded and targets up, every bill equal to `compute_bill()`, reconciliation present, projection populated."));
if (smoke) S.push(code(smoke));
S.push(bullet("**Reproduce:** `docker compose up --build -d`, wait ~6 minutes for the first bill, then `python scripts/smoke_test.py --wait-billing`. All configuration is in `config.py` / `.env`."));

// ================================================================= 8
S.push(h1("8. Results"));
S.push(p(`The results below come from one continuous run of the stack (${recon.length} simulated days, ~${Math.round(recon.length * 5)} minutes of real time). Every number was read from the API by \`report/capture_results.py\`.`));
S.push(h2("8.1 Live dashboard and real-time API"));
S.push(...figure("screenshots/dashboard_top.png", "Live dashboard: speed-layer KPIs, per-zone renewable % with the alert threshold, 15-minute history, active alerts and pipeline health.", 6.5));
S.push(...figure("screenshots/api_grid_live.png", "GET /api/grid/live — latest complete window per zone (speed view).", 5.2, 7.0));
S.push(h2("8.2 Daily billing and solar-contribution report (batch view)"));
S.push(p(`For simulated day ${billing.sim_day}, the batch layer billed ${billing.count} households for a total of LKR ${money(billing.total_billed)}. Zone roll-up:`));
S.push(table(["Zone", "Households", "Consumption kWh", "Solar kWh", "Avg solar contribution %", "Billed (LKR)"],
  summary.zones.map((z) => [z.grid_zone, z.households, f2(z.total_consumption_kwh), f2(z.total_solar_kwh), f2(z.avg_solar_contribution_pct, 1), money(z.total_billed)]),
  [1400, 1300, 1800, 1500, 2150, 1700]));
S.push(spacer());
S.push(p("First rows of the per-household report (`reports/daily_billing_report_simdayN.csv`):"));
S.push(table(["Household", "Zone", "Tier", "Net kWh", "Solar %", "Tariff", "Source", "Subsidy", "Bill (LKR)"],
  billing.rows.slice(0, 8).map((r) => [r.household_id, r.grid_zone, r.billing_tier.replace("residential_", ""), f2(r.net_consumption_kwh), f2(r.solar_contribution_pct, 1), f2(r.tariff_rate), r.tariff_source === "current_day" ? "today" : "fallback", r.subsidy_flag ? "yes" : "no", money(r.bill_amount)]),
  [1100, 900, 1150, 1000, 900, 900, 1050, 900, 1250]));
S.push(spacer());
S.push(...figure("screenshots/report_file.png", "Scheduled consolidated report file written by the Airflow publish_report task.", 6.2, 7.5));
S.push(h2("8.3 Lambda merge: provisional bills during the day"));
const pr = projection.rows.find((r) => r.household_id === "H-001") || projection.rows[0];
if (pr) S.push(p(`At capture time (sim day ${projection.clock.sim_day}, ${projection.clock.sim_time_of_day}) household ${pr.household_id} had consumed ${f2(pr.consumption_kwh)} kWh with ${f2(pr.solar_kwh)} kWh of solar according to the speed layer; applying its latest batch-validated tariff (${f2(pr.tariff_rate)} LKR/kWh, from day ${pr.tariff_sim_day}) gives a provisional bill so far of LKR ${money(pr.provisional_bill_so_far)}, next to its final bill of LKR ${pr.last_final_bill === null ? "–" : money(pr.last_final_bill)} for day ${pr.last_final_sim_day}. The provisional total for all 24 households was LKR ${money(projection.total_provisional)}. Figure 8 shows the same endpoint for this household, queried a few seconds later (the figures grow as readings arrive).`));
S.push(...figure("screenshots/api_projection.png", "GET /api/billing/projection — speed-layer consumption merged with the batch-layer tariff.", 5.2, 6.5));
S.push(h2("8.4 Speed vs batch reconciliation and data quality"));
S.push(table(["Sim day", "Raw events", "Dup. removed", "Speed kWh", "Batch kWh", "Drift %", "Invalid tariff rows", "Fallback tariffs", "Billed (LKR)"],
  recon.map((r) => [r.sim_day, r.raw_events, r.duplicates_removed, f2(r.speed_consumption_kwh), f2(r.batch_consumption_kwh), f2(r.drift_pct), r.invalid_tariff_rows, r.fallback_tariffs, money(r.total_billed)]),
  [800, 1050, 1050, 1150, 1150, 900, 1250, 1150, 1300]));
S.push(spacer());
const dupDays = recon.filter((r) => r.duplicates_removed > 0).map((r) => r.sim_day);
const tariffDefects = recon.filter((r) => r.invalid_tariff_rows > 0 || r.duplicate_tariff_rows > 0);
S.push(p(`Over the run the batch layer read ${totalRaw.toLocaleString("en-US")} events from the lake and removed ${totalDup} duplicates${dupDays.length ? ` (days ${dupDays.join(", ")})` : ""}. These are redelivered readings that arrived in a later micro-batch than the original, so the speed layer's in-batch dedup could not see them and its running total counted them twice — a positive drift is exactly that over-count, and the batch layer's global dedup on \`event_id\` removes it from the final bill. Days with zero drift had no cross-batch duplicates. ${tariffDefects.length ? `Tariff defects occurred on day(s) ${tariffDefects.map((r) => r.sim_day).join(", ")}: the invalid or duplicated rows were rejected and ${recon.reduce((a, r) => a + r.fallback_tariffs, 0)} household(s) were billed with their previous valid tariff instead.` : "No tariff defects occurred in this run's files."} Days 1 and 2 also span the 3.5-minute producer outage of the failure drill (section 6.1), which lowers their consumption and bills but not their correctness: both layers saw the same, smaller set of events.`));
const q = status.stream_quality_last_5m;
S.push(p(`In the last 5 minutes before capture the speed layer processed ${q.total_events} events across ${q.micro_batches} micro-batches, quarantined ${q.invalid_events} (${f2(q.invalid_rate_pct)}%; ${Object.entries(q.invalid_by_reason).map(([k, v]) => `${k}: ${v}`).join(", ") || "none"}), dropped ${q.duplicate_events} in-batch duplicates, with an average event-to-sink lag of ${f2(q.avg_lag_seconds, 1)} s.`));
S.push(h2("8.5 Alerts, orchestration and monitoring"));
const lowR = [...alertsOpen, ...alertsResolved].filter((a) => a.alert_type === "LOW_RENEWABLE");
const byZone = {};
for (const a of lowR) byZone[a.scope] = (byZone[a.scope] || 0) + 1;
S.push(p(`Alerts raised during the run, by type: ${Object.entries(alertCounts).map(([k, v]) => `${k} × ${v}`).join(", ") || "none"}. The LOW_RENEWABLE alerts by zone were ${Object.entries(byZone).map(([k, v]) => `${k} × ${v}`).join(", ")}: South, which has the least installed solar, drops below 10% at the start of simulated daylight every day, and the other zones triggered only while under that day's overcast spell. Every one auto-resolved within one or two 15 s checks once the next window recovered. The two NO_DATA alerts are the failure drill of section 6.1. Because the rule has no minimum duration, a zone hovering around the threshold can raise short alerts; section 9 lists the fix.`));
S.push(...figure("screenshots/prometheus_alerts.png", "Prometheus: alert rules from alert_rules.yml loaded and evaluated.", 6.3, 6.5));
S.push(...figure("screenshots/spark_streaming.png", "Spark UI: the two Structured Streaming queries (zone_metrics, raw_lake).", 6.3, 5.0));

// ================================================================= 9
S.push(h1("9. Limitations, Trade-offs and Production-Scale Changes"));
S.push(table(["Area", "Simplification in this project", "What we would do at production scale"], [
  ["Kafka", "1 broker, replication factor 1, no auth", "≥3 brokers, RF=3, min.insync.replicas=2, idempotent producer, TLS/SASL, schema registry (Avro) for evolvable event schemas"],
  ["Spark", "local[2] in a container; batch Spark runs inside the Airflow container", "Spark on Kubernetes/YARN; SparkSubmitOperator or KubernetesPodOperator; autoscaling"],
  ["Speed-layer accuracy", "At-least-once: in-batch dedup only; additive running totals can double count after a crash", "Stateful dedup with watermark or transactional sinks for exactly-once; keep the batch layer as the source of truth either way"],
  ["Late data", "Events later than the 1-minute watermark are dropped from windows (still in the lake)", "Tune watermark from observed lateness; re-run the batch day if late data arrives after billing"],
  ["Airflow", "Standalone, SequentialExecutor, SQLite metadata", "Celery/Kubernetes executor with a Postgres metadata DB; data-aware scheduling (Datasets) triggered by the tariff file"],
  ["Data lake", "Local Docker volume, Parquet", "S3/HDFS with a table format (Delta/Iceberg) for ACID appends, compaction and time travel"],
  ["Serving", "Single Postgres, no auth, dashboard polls every 5 s", "Read replicas or a time-series store (TimescaleDB) for live metrics; API auth; push updates (WebSocket)"],
  ["Observability", "Home-grown rule engine + single Prometheus, no Grafana/Alertmanager; LOW_RENEWABLE has no minimum duration, so it can flap near the threshold", "Alert hysteresis (e.g. breach for 2 min, clear above 12%), Alertmanager routing/on-call, Grafana dashboards, OpenTelemetry tracing, central log store"],
  ["Billing", "Flat per-kWh tariff, one subsidy rule, no export credit", "Tiered/time-of-use tariffs, net-metering credits, versioned tariffs and an audit trail"],
  ["Simulation", "24 households, 5-minute days", "Real meter volumes need more partitions and a partitioning scheme by zone/date"],
], [1400, 3900, 4550]));
S.push(spacer());
S.push(p("**What we would do differently.** We would introduce a schema registry from day one (the ad-hoc JSON schema is the main source of dirty-data risk), use a table format such as Delta Lake so the batch layer could do atomic per-day overwrites directly in the lake, and move the renewable rule to a forecast-aware threshold (expected solar for the hour and weather) instead of a fixed 10%."));

// ================================================================= 10
S.push(h1("10. Conclusion"));
S.push(p("The platform ingests a continuous meter stream and a daily tariff extract, answers the business question in real time (grid load and renewable mix by zone) and per day (exact household bills and solar contribution), and shows both views plus their merge in one API and dashboard. Lambda was chosen because the use case combines a low-latency monitoring need with a correctness-critical, replayable daily computation over a naturally batch source, and the measured speed-versus-batch drift shows why the batch layer is needed. The pipeline is observable at every stage through structured logs, heartbeats, quality and lag metrics, seven alert rules and Prometheus."));
S.push(h2("Statement of contribution and use of AI tools"));
S.push(p("Individual submission: all design, implementation, testing and writing by the author. (For a group submission, replace this with one line per member naming the components they owned.) AI coding assistance was used for boilerplate, as the module rules permit; every architectural decision and all core pipeline logic were reviewed and can be explained and defended by the author."));

// ---------------------------------------------------------------- build
const doc = new Document({
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 30, color: NAVY, font: FONT },
        paragraph: { spacing: { before: 300, after: 140 }, keepNext: true, border: { bottom: { color: ACCENT, space: 4, style: BorderStyle.SINGLE, size: 8 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 24, color: ACCENT, font: FONT },
        paragraph: { spacing: { before: 220, after: 100 }, keepNext: true } },
    ],
  },
  numbering: { config: [] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, bottom: 1000, left: 1030, right: 1030 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "EC8203 Mini Project — Smart Grid Lambda Pipeline", size: 16, color: "888888", font: FONT })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, font: FONT })] })] }) },
    children: S,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(R("EC8203_MiniProject_Report.docx"), buf);
  console.log("wrote report/EC8203_MiniProject_Report.docx");
});
