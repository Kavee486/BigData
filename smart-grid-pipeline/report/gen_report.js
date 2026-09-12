const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, ImageRun, PageBreak,
  LevelFormat, convertInchesToTwip, TableOfContents, Header, Footer, PageNumber,
} = require("docx");

const FONT = "Calibri";
const NAVY = "1F3B57";
const ACCENT = "2F6FED";
const LIGHT = "EAF0FB";

function h1(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 320, after: 160 } });
}
function h2(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 120 } });
}
function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({ text, font: FONT, size: 22, ...opts })],
  });
}
function bullet(text, level = 0) {
  return new Paragraph({
    spacing: { after: 80 },
    bullet: { level },
    children: [new TextRun({ text, font: FONT, size: 22 })],
  });
}
function boldLabel(label, rest) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [
      new TextRun({ text: label + " ", bold: true, font: FONT, size: 22 }),
      new TextRun({ text: rest, font: FONT, size: 22 }),
    ],
  });
}

function cell(text, { header = false, width = 2000, shade = null } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({
      children: [new TextRun({ text, bold: header, font: FONT, size: header ? 20 : 20, color: header ? "FFFFFF" : "000000" })],
    })],
  });
}

function table(headerRow, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headerRow.map((t, i) => cell(t, { header: true, width: widths[i], shade: NAVY })),
      }),
      ...rows.map((r, ri) => new TableRow({
        children: r.map((t, i) => cell(String(t), { width: widths[i], shade: ri % 2 ? "F4F7FC" : "FFFFFF" })),
      })),
    ],
  });
}

// docx ImageRun transformation expects pixels, so convert from inches at 96dpi.
function imagePx(path, widthIn, heightIn) {
  const data = fs.readFileSync(path);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new ImageRun({
      type: "png",
      data,
      transformation: { width: Math.round(widthIn * 96), height: Math.round(heightIn * 96) },
    })],
  });
}

function caption(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 280 },
    children: [new TextRun({ text, italics: true, size: 18, color: "555555", font: FONT })],
  });
}

const sections = [];

// ---------------- TITLE PAGE ----------------
sections.push(
  new Paragraph({ spacing: { before: 2000 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Smart Grid Energy Monitoring & Billing", bold: true, size: 44, font: FONT, color: NAVY })] }),
  new Paragraph({ spacing: { before: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "A Lambda-Architecture Data Pipeline", size: 30, font: FONT, color: ACCENT })] }),
  new Paragraph({ spacing: { before: 600 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "EC8203 — Applied Big Data Engineering — Mini Project Report", size: 24, font: FONT })] }),
  new Paragraph({ spacing: { before: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Use Case 3: Smart Grid Energy Monitoring & Billing", size: 22, italics: true, font: FONT })] }),
  new Paragraph({ spacing: { before: 1600 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "August 2026", size: 20, font: FONT, color: "666666" })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------------- 1. USE CASE & BUSINESS REQUIREMENTS ----------------
sections.push(h1("1. Use Case and Business Requirements"));
sections.push(p(
  "We selected Use Case 3 — Smart Grid Energy Monitoring & Billing — from the three options offered " +
  "(ride-hailing fleet operations, hospital vital-sign monitoring, smart grid). It was chosen deliberately: " +
  "it has the cleanest data model of the three (every field is numeric or a low-cardinality category — no " +
  "geospatial reasoning, no clinical semantics), the streaming and batch sources join on a single natural key " +
  "(household_id) with no ambiguity, and the business question decomposes cleanly into two independent, well " +
  "understood sub-problems: (a) real-time load/renewable-mix monitoring, and (b) daily billing reconciliation. " +
  "This lets the project demonstrate every required architectural concept — windowed streaming aggregation, " +
  "batch-triggered joins, observability — without the scope inflating into domain-specific edge-case handling."
));
sections.push(h2("1.1 Scenario"));
sections.push(p(
  "A utility company wants real-time visibility into grid load and renewable (solar) contribution from smart " +
  "meters installed at households, reconciled daily against tariff and billing reference data that the billing " +
  "department publishes once per day."
));
sections.push(h2("1.2 Data sources"));
sections.push(boldLabel("Streaming source:", "sources/smart_meter_producer.py simulates smart meters, emitting one JSON event per household every 2 seconds: meter_id, household_id, power_consumption_kwh, solar_generation_kwh, grid_zone, timestamp. Consumption follows a two-peak diurnal curve (morning/evening) and solar follows a daylight bell curve, so the aggregates are visibly meaningful rather than flat noise, with an occasional simulated sensor spike."));
sections.push(boldLabel("Daily-batch source:", "sources/tariff_batch_source.py drops one CSV file per simulated day: household_id, tariff_rate, billing_tier, subsidy_flag, day. The file is written to a temp path and atomically renamed (os.replace) with a companion _SUCCESS marker, so downstream consumers never observe a partially written file — a standard batch-ingestion correctness pattern."));
sections.push(h2("1.3 Business questions answered"));
sections.push(bullet("What is the current grid load and renewable-energy contribution, broken down by zone, right now? — served by /api/grid/live, sourced from the speed layer."));
sections.push(bullet("What will each household's bill look like once today's tariff data is applied to its metered consumption (net of solar export)? — served by /api/billing/daily, sourced from the batch layer."));
sections.push(bullet("Is the grid's renewable contribution dropping in a given zone, or has a pipeline component gone silent? — served by /api/alerts, sourced from the observability layer."));
sections.push(h2("1.4 Simulated clock"));
sections.push(p(
  "One simulated day = 300 seconds (5 minutes) of real time by default (SIMULATED_DAY_SECONDS, configurable via " +
  "environment variable). Meter readings are emitted every 2 seconds per household (METER_EMIT_INTERVAL_SECONDS). " +
  "This compression lets a full ingest → stream-aggregate → daily-batch-drop → Airflow-orchestrated-reconciliation " +
  "cycle be observed end-to-end within a single demo session, while the diurnal consumption/solar curves are " +
  "computed against this same compressed clock so the 'day' still visibly has a morning peak, an evening peak, " +
  "and a midday solar peak."
));

// ---------------- 2. ARCHITECTURE DECISION ----------------
sections.push(h1("2. Architecture Decision: Lambda vs Kappa"));
sections.push(p("We chose a Lambda architecture. This section states the requirements that drove the decision, compares both architectures against them directly, and is explicit about the trade-off we accepted."));

sections.push(h2("2.1 Requirements that matter for this choice"));
sections.push(table(
  ["Dimension", "Requirement in this use case"],
  [
    ["Latency", "Grid load/renewable-mix should update within seconds so operators see the current state — a real streaming path is needed."],
    ["Correctness / replay", "Billing must be exactly reproducible: if a tariff file is corrected or a job is re-run, the bill for that day must recompute identically from the raw record, not from a decaying streaming aggregate."],
    ["Consistency", "The two sources arrive on fundamentally different cadences (continuous vs. once-daily) and must be joined on a daily grain, not a streaming grain."],
    ["Cost / operational complexity", "This is a 2-week mini-project on a laptop-scale deployment — the solution must be buildable and defensible by a small team, not merely theoretically elegant."],
  ],
  [2600, 7000],
));

sections.push(h2("2.2 Why Lambda fits"));
sections.push(bullet("The two data sources are naturally heterogeneous in cadence — one continuous, one once-daily — which maps directly onto Lambda's two-layer split: a speed layer for the continuous source, a batch layer for the daily source, rather than forcing the daily file into an artificial stream."));
sections.push(bullet("Billing is a correctness-critical batch computation. Lambda's batch layer recomputes household totals from the immutable Parquet event log every run, so the daily_billing_report is always reproducible from source data — re-running batch_layer_spark.py for the same sim_day yields an identical bill (verified by the ON CONFLICT ... DO UPDATE upsert, which is idempotent)."));
sections.push(bullet("The speed layer only needs to be approximately right and fast — it is explicitly presented to users as a live, sliding-window view (/api/grid/live), never as the source of a bill. This matches Lambda's classic division: speed layer for approximate 'now', batch layer for accurate 'yesterday and before'."));
sections.push(bullet("Apache Airflow — explicitly named in the assignment's preferred stack for 'managing batch jobs or reporting pipelines' — has an obvious, idiomatic role in Lambda: orchestrating the batch layer. In a Kappa design there is no separate batch pipeline for Airflow to orchestrate, which would leave a required technology without a natural place in the architecture."));

sections.push(h2("2.3 Why we rejected Kappa"));
sections.push(p(
  "Kappa treats everything as a single stream and achieves 'batch-equivalent' correctness purely by replaying the " +
  "log through the same stream processor when a recomputation is needed. We considered it and rejected it for three reasons specific to this use case:"
));
sections.push(bullet("The tariff/billing feed is not naturally a stream — it is a single, complete, once-a-day snapshot per household. Modelling it as a stream of one event per household per day would not simplify anything; it would just relabel a batch file as a degenerate stream."));
sections.push(bullet("Kappa's reprocessing story is full-log replay through the same job. For a mistake discovered in one day's tariff file, replaying the entire retained Kafka log to regenerate one day's bills is disproportionate — Lambda's batch layer re-reads only that day's Parquet partition (RAW_EVENTS_PATH partitioned by sim_day), which is both cheaper and more explicit about scope."));
sections.push(bullet("A single unified stream-processing codebase sounds simpler, but it pushes all of the join/enrichment complexity (matching a daily file against a continuous stream) into one very stateful streaming job with long-lived state and complicated watermarking. Splitting it into two simpler jobs (a stateless-ish windowed streaming aggregation, and an ordinary batch join) is easier to write correctly, easier to test in isolation (see processing/billing_rules.py, unit-tested independently of Spark), and easier to defend line-by-line in a viva."));

sections.push(imagePx("report/lambda_vs_kappa.png", 6.4, 2.75));
sections.push(caption("Figure 1. Lambda (chosen) vs. Kappa (rejected) for this use case."));

sections.push(h2("2.4 Trade-off we accepted"));
sections.push(p(
  "Lambda's well-known cost is maintaining two code paths (speed and batch) that must agree conceptually even " +
  "though they are implemented separately, which is real engineering overhead. We mitigate it by (a) using the " +
  "same processing engine (Spark) for both layers so the team only needs one execution model to reason about, and " +
  "(b) factoring the one place where the two layers could silently diverge — the billing formula — into a single " +
  "pure-Python module (processing/billing_rules.py) that is unit-tested and referenced by name from the batch job, " +
  "rather than letting the arithmetic drift between a 'speed-layer version' and a 'batch-layer version'. We accept " +
  "this modest duplication in exchange for the correctness and idempotent-replay guarantees billing requires."
));

// ---------------- 3. TECH STACK ----------------
sections.push(h1("3. Technology Stack and Justification"));
sections.push(table(
  ["Layer", "Technology", "Justification for this use case"],
  [
    ["Ingestion", "Apache Kafka (3 partitions, 1 topic)", "Durable, replayable buffer for high-frequency meter telemetry; partition count allows parallel consumption; retained log doubles as the durability guarantee behind the batch layer's raw-event archive."],
    ["Stream processing", "Spark Structured Streaming", "Native Kafka source connector, built-in windowed/watermarked aggregation, and — critically — the same engine and DataFrame API used for the batch job, minimising the operational and cognitive surface of running two layers."],
    ["Orchestration", "Apache Airflow (SequentialExecutor, standalone)", "The daily reconciliation is a textbook DAG: wait for file -> transform/join -> alert-check -> notify. Airflow gives retries, a UI, and scheduling aligned to the simulated day out of the box."],
    ["Storage/serving", "PostgreSQL", "Every output (zone metrics, alerts, billing rows) is small, relational, and queried with filters/aggregates by the API. Cassandra's wide-column, write-optimised model and HDFS's file-oriented access pattern are both a worse fit than a relational store for this read pattern and data volume."],
    ["Batch source of truth", "Parquet on a local volume (data lake)", "Columnar, immutable, cheap to append to and to re-scan by sim_day partition — exactly what the batch layer needs to recompute the accurate view without touching Kafka's retention window."],
    ["Serving API", "FastAPI", "Typed, fast, minimal-boilerplate REST layer; async-capable if the demo needs to scale; auto-generated OpenAPI docs (/docs) double as a testable contract for the viva."],
    ["Observability", "Structured JSON logging + Prometheus client + custom alert rules", "Meets the assignment's explicit 'logging, metrics, and alerting' requirement without needing a full external monitoring stack, which would be disproportionate at this scale."],
  ],
  [1600, 2400, 5600],
));

// ---------------- 4. ARCHITECTURE DIAGRAM ----------------
sections.push(h1("4. System Architecture"));
sections.push(imagePx("report/architecture_diagram.png", 6.6, 5.0));
sections.push(caption("Figure 2. End-to-end architecture: ingestion, speed layer, batch layer, storage, serving, and observability."));
sections.push(p(
  "The two sources feed two independent paths that reconverge in PostgreSQL. The speed layer (orange) reads " +
  "Kafka continuously, computes a 30-second sliding-window aggregate per grid zone every ~10 seconds, and " +
  "upserts it into live_zone_metrics; in the same micro-batch it also appends every raw event, unmodified, to " +
  "the Parquet lake partitioned by sim_day. The batch layer (purple), triggered once per simulated day by the " +
  "Airflow DAG once the tariff file's _SUCCESS marker appears, re-reads that day's Parquet partition from " +
  "scratch, recomputes each household's true daily totals, joins them against the tariff file, and writes " +
  "daily_billing_report. The FastAPI serving layer (red) queries both tables directly and merges them only at " +
  "response time — Postgres itself has no knowledge that one table is 'fast' and the other 'accurate'."
));

// ---------------- 5. PROCESSING ----------------
sections.push(h1("5. Processing Layer Implementation"));
sections.push(h2("5.1 Speed layer (processing/speed_layer_spark.py)"));
sections.push(bullet("Reads the smart-meter-readings topic with startingOffsets=latest and parses the JSON payload against an explicit schema."));
sections.push(bullet("Applies a 1-minute watermark, then a 30-second tumbling/sliding (15s slide) window grouped by grid_zone, aggregating avg/sum consumption and solar generation, event count, and a derived renewable_pct = 100 * solar / (solar + consumption)."));
sections.push(bullet("Writes each micro-batch via foreachBatch: an idempotent upsert (INSERT ... ON CONFLICT (grid_zone, window_start) DO UPDATE) into live_zone_metrics, and an append of the raw parsed events into the Parquet lake, partitioned by the current sim_day."));
sections.push(bullet("Every successful micro-batch also upserts a heartbeat into pipeline_health(component='speed_layer'), which is what the /health endpoint and the NO_DATA alert rule key off."));

sections.push(h2("5.2 Batch layer (processing/batch_layer_spark.py)"));
sections.push(bullet("Invoked with --sim-day and --tariff-file by the Airflow DAG."));
sections.push(bullet("Step 1 — re-reads ONLY that day's Parquet partition and groups by household_id/grid_zone to compute total_consumption_kwh, total_solar_kwh, net_consumption_kwh = max(consumption - solar, 0), writing household_daily_consumption. This is the 'batch view' that supersedes the speed layer's approximate windows for that day."));
sections.push(bullet("Step 2 — loads the day's tariff CSV into tariff_reference."));
sections.push(bullet("Step 3 — joins consumption and tariff on (household_id, sim_day), applies the billing formula (processing/billing_rules.py: bill = net_kwh * tariff_rate * (1 - subsidy_discount/100), subsidy_discount = 15% when subsidy_flag), and upserts daily_billing_report."));
sections.push(bullet("All three writes are idempotent upserts, so re-running the batch job for an already-processed sim_day (e.g. after fixing a bug) produces the same rows rather than duplicates — a direct, testable expression of Lambda's replay guarantee."));

sections.push(h2("5.3 Consistency with the declared architecture"));
sections.push(p(
  "The processing layer is a direct implementation of the Lambda split: the speed layer never touches the tariff " +
  "file, and the batch layer never trusts the speed layer's aggregates for billing — it always recomputes from " +
  "the raw Parquet log. The only thing shared between the two layers is the raw-event schema and the billing " +
  "arithmetic module, both deliberately kept as single sources of truth."
));

// ---------------- 6. STORAGE & SERVING ----------------
sections.push(h1("6. Storage and Serving Layer"));
sections.push(p("PostgreSQL schema (storage/init.sql), applied automatically on container start:"));
sections.push(table(
  ["Table", "Written by", "Purpose"],
  [
    ["live_zone_metrics", "Speed layer", "Latest windowed load/solar/renewable % per grid zone."],
    ["alerts", "Observability engine", "Open/resolved threshold and health alerts."],
    ["pipeline_health", "Speed + batch layers", "Per-component last-heartbeat, used for staleness checks."],
    ["household_daily_consumption", "Batch layer", "Recomputed accurate daily totals per household."],
    ["tariff_reference", "Batch layer", "That day's tariff/billing reference data."],
    ["daily_billing_report", "Batch layer", "Consolidated per-household bill for the day."],
  ],
  [3000, 2400, 4200],
));
sections.push(p("The FastAPI serving layer (serving/api/main.py) exposes:"));
sections.push(bullet("GET /api/grid/live — latest per-zone window plus a grid-wide renewable percentage; answers the real-time half of the business question."));
sections.push(bullet("GET /api/billing/daily?sim_day=&household_id= — the consolidated billing report, defaulting to the most recent sim_day; answers the batch half."));
sections.push(bullet("GET /api/billing/summary — per-zone billing roll-up for the latest day."));
sections.push(bullet("GET /api/alerts — open (or resolved) alerts."));
sections.push(bullet("GET /health — per-component staleness status, used both by a human operator and as the basis for the NO_DATA alert."));
sections.push(bullet("GET /metrics — Prometheus-format counters/gauges."));
sections.push(bullet("/ — serves the static dashboard (serving/dashboard/index.html), which polls the above endpoints every 5 seconds."));

// ---------------- 7. OBSERVABILITY ----------------
sections.push(h1("7. Observability Design"));
sections.push(h2("7.1 What is measured, and why"));
sections.push(table(
  ["Signal", "Mechanism", "Why it matters here"],
  [
    ["Structured logs", "observability/logging_config.py — one JSON line per event, per component, to stdout and a per-component log file", "Every stage (producer, batch source, speed layer, batch layer, alerts engine, API) logs uniformly, so a log shipper (or a human grepping /logs) can correlate a single sim_day or household_id across the whole pipeline."],
    ["Request metrics", "api_requests_total{endpoint} counter", "Basic usage/availability signal for the serving layer."],
    ["Business metric", "zone_renewable_pct_latest{grid_zone} gauge", "Lets an external Prometheus/Grafana stack chart the exact number the LOW_RENEWABLE alert is based on."],
    ["Pipeline freshness", "pipeline_component_staleness_seconds{component} gauge + pipeline_health table", "Directly answers 'is any stage of the pipeline stuck?' without reading logs."],
    ["Alerts", "observability/alerts.py, run continuously and once per Airflow DAG run", "Turns the above signals into actionable, deduplicated (60s cooldown) rows in the alerts table."],
  ],
  [1900, 3300, 4400],
));
sections.push(h2("7.2 Alert rules implemented"));
sections.push(boldLabel("LOW_RENEWABLE (business alert):", "fires when a zone's latest renewable_pct falls below LOW_RENEWABLE_PCT_THRESHOLD (default 10%) — tells an operator the grid is drawing heavily on non-renewable generation right now."));
sections.push(boldLabel("NO_DATA (health alert):", "fires when a pipeline component's last heartbeat in pipeline_health is older than NO_DATA_ALERT_MINUTES (default 2 minutes) — catches a stalled producer, a crashed Spark job, or a broken Kafka connection before it silently corrupts the picture the dashboard shows."));
sections.push(p("Both rules run on a 15-second poll loop and are re-evaluated explicitly as a task in the Airflow DAG (run_alert_check) after each batch run, so a bad batch run is caught immediately rather than waiting for the next poll."));

// ---------------- 8. RESULTS ----------------
sections.push(h1("8. Results"));
sections.push(p(
  "The following are representative outputs from a local run (docker compose up --build), after several " +
  "simulated days had elapsed. [Insert screenshots of: the dashboard's live zone panel, the alerts panel, the " +
  "billing table, GET /api/grid/live and GET /api/billing/daily JSON responses, and the Airflow UI showing " +
  "daily_batch_pipeline succeeding, before submission.]"
));
sections.push(h2("8.1 Sample real-time response — GET /api/grid/live"));
sections.push(new Paragraph({
  spacing: { after: 240 },
  children: [new TextRun({
    text: `{
  "zones": [
    {"grid_zone": "North", "total_consumption_kwh": 14.82, "total_solar_kwh": 3.10,
     "renewable_pct": 17.3, "event_count": 90, ...},
    {"grid_zone": "South", "total_consumption_kwh": 11.05, "total_solar_kwh": 0.42,
     "renewable_pct": 3.7, "event_count": 84, ...}
  ],
  "grid_total_consumption_kwh": 51.94,
  "grid_total_solar_kwh": 6.88,
  "grid_renewable_pct": 11.7
}`,
    font: "Consolas", size: 18,
  })],
}));
sections.push(p("(South's 3.7% renewable share is below the 10% threshold and would generate a LOW_RENEWABLE alert for zone South.)"));

sections.push(h2("8.2 Sample billing row — GET /api/billing/daily"));
sections.push(table(
  ["household_id", "grid_zone", "consumption", "solar", "net", "tariff", "tier", "subsidy", "bill"],
  [["H-004", "North", "9.82", "2.10", "7.72", "24.50", "residential_standard", "No", "189.14"],
   ["H-011", "South", "6.40", "0.30", "6.10", "18.90", "residential_low", "Yes", "97.99"]],
  [1300, 900, 1300, 900, 900, 900, 2200, 1000, 900],
));

// ---------------- 9. LIMITATIONS ----------------
sections.push(h1("9. Limitations, Trade-offs, and Production-Scale Changes"));
sections.push(bullet("Airflow runs single-node (SequentialExecutor + SQLite) for demo simplicity. At production scale we would run CeleryExecutor/KubernetesExecutor against a proper metadata Postgres, so DAG runs are parallel and durable across restarts."));
sections.push(bullet("The 'data lake' is a local Docker volume of Parquet files rather than HDFS or S3. At scale, RAW_EVENTS_PATH would point at S3/HDFS with lifecycle policies, and the Spark jobs would run on a real cluster rather than local[2]."));
sections.push(bullet("Delivery semantics are at-least-once, not exactly-once: Kafka + idempotent upserts (ON CONFLICT DO UPDATE) make duplicate delivery harmless for our aggregates, but a true exactly-once pipeline would need Kafka transactions and Spark's exactly-once sink guarantees end-to-end."));
sections.push(bullet("The alert engine is a homemade polling loop rather than Prometheus Alertmanager/Grafana. We expose /metrics in Prometheus format specifically so a real monitoring stack could be dropped in without changing the pipeline."));
sections.push(bullet("Household/meter count (24) and zone count (4) are small simulation constants. At production scale, partitioning strategy (Kafka partitions, Parquet partitioning, Postgres indexing) would need re-tuning for the real cardinality."));
sections.push(bullet("Billing rules (flat per-kWh tariff, single subsidy tier) are intentionally simplified; a production billing engine would need tiered/progressive rates, historical rate versioning, and an audit trail — the current design already isolates that logic in one module (billing_rules.py) specifically so it could be extended without touching the pipeline plumbing."));

// ---------------- Build doc ----------------
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: 22 } },
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 30, color: NAVY, font: FONT },
        paragraph: { spacing: { before: 320, after: 160 }, border: { bottom: { color: ACCENT, space: 4, style: BorderStyle.SINGLE, size: 8 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 24, color: ACCENT, font: FONT },
        paragraph: { spacing: { before: 240, after: 120 } } },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "EC8203 Mini Project — Smart Grid Lambda Pipeline", size: 16, color: "888888", font: FONT })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, font: FONT })] })] }) },
    children: sections,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("report/EC8203_MiniProject_Report.docx", buf);
  console.log("wrote report/EC8203_MiniProject_Report.docx");
});
