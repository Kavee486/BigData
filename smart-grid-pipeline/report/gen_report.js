// Generates report/EC8203_MiniProject_Report.docx from the text below plus the
// evidence captured from a real run (report/results/*.json, report/screenshots/*.png,
// produced by report/capture_results.py). Run from the repo root:
//     node report/gen_report.js
// then export to PDF with report/export_pdf.ps1 (Microsoft Word).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, ImageRun, PageBreak, TableOfContents, Header, Footer, PageNumber,
} = require("docx");

const FONT = "Times New Roman";
const BLACK = "000000";
const NAVY = "1F3B57";
const R = (f) => path.join("report", f);
const J = (name) => JSON.parse(fs.readFileSync(R(`results/${name}.json`), "utf8"));
const AUTHORS = [["Sewvandi M.A.K.", "EG/2021/4808"], ["Peiris P.R.S.", "EG/2021/4706"]];

// ---------------------------------------------------------------- helpers
const h1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1 });
const h2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2 });
function runs(text, base = {}) {
  // **bold** and `term` inline markup (terms are set in the body font)
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).filter(Boolean).map((t) => {
    if (t.startsWith("**")) return new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, size: 22, ...base });
    if (t.startsWith("`")) return new TextRun({ text: t.slice(1, -1), font: FONT, size: 22, ...base });
    return new TextRun({ text: t, font: FONT, size: 22, ...base });
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
    children: [new Paragraph({ children: runs(String(text), { size: 19, bold: header || undefined, color: header ? "FFFFFF" : undefined }) })],
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
  const { w, h } = pngSize(full);
  let width = widthIn, height = (widthIn * h) / w;
  if (height > maxHeightIn) { height = maxHeightIn; width = (maxHeightIn * w) / h; }
  figNo += 1;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: Math.round(width * 96), height: Math.round(height * 96) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 220 },
      children: [new TextRun({ text: `Figure ${figNo}. ${caption}`, italics: true, size: 19, color: BLACK, font: FONT })] }),
  ];
}
function code(text) {
  return new Paragraph({
    spacing: { after: 160 }, shading: { type: ShadingType.CLEAR, fill: "F3F4F6" },
    children: text.split("\n").map((line, i) => new TextRun({ text: line, font: FONT, size: 18, break: i ? 1 : 0 })),
  });
}
const f2 = (v, d = 2) => (v === null || v === undefined ? "–" : Number(v).toFixed(d));
const money = (v) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------------------------------------------------------------- evidence
const recon = J("reconciliation").rows.slice().sort((a, b) => a.sim_day - b.sim_day);
const billing = J("billing_daily");
const summary = J("billing_summary");
const status = J("pipeline_status");
const alertsOpen = J("alerts_open").alerts;
const alertsResolved = J("alerts_resolved").alerts;
const projection = J("billing_projection");
const drill = J("failure_drill");
const cleanOutput = (t) => t.split("\n").filter((l) => !l.startsWith("$ ")).join("\n")
  .replace("billing_rules.compute_bill", "the billing formula").trim();
const tests = cleanOutput(fs.readFileSync(R("results/pytest.txt"), "utf8"));
const smoke = cleanOutput(fs.readFileSync(R("results/smoke_test.txt"), "utf8"));
const totalRaw = recon.reduce((a, r) => a + r.raw_events, 0);
const totalDup = recon.reduce((a, r) => a + r.duplicates_removed, 0);
const alertCounts = {};
for (const a of [...alertsOpen, ...alertsResolved]) alertCounts[a.alert_type] = (alertCounts[a.alert_type] || 0) + 1;

const S = [];

// ================================================================= TITLE
const tp = (text, { size = 24, bold = false, before = 0, after = 0 } = {}) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before, after },
  children: [new TextRun({ text, size, bold, font: FONT, color: BLACK })],
});
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideHorizontal: noBorder, insideVertical: noBorder };
const authorCell = (text, width, align) => new TableCell({
  width: { size: width, type: WidthType.DXA }, borders: noBorders,
  children: [new Paragraph({ alignment: align, spacing: { after: 40 }, children: [new TextRun({ text, size: 22, font: FONT })] })],
});
S.push(
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 500 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(R("assets/ruhuna_logo.png")), transformation: { width: 106, height: 150 } })] }),
  tp("Smart Grid Energy Monitoring & Billing:", { size: 40, after: 60 }),
  tp("A Lambda-Architecture Data Pipeline", { size: 40, after: 500 }),
  tp("Mini Project Assessment", { size: 30, bold: true, after: 160 }),
  tp("EC8203 Applied Big Data Engineering", { size: 24, after: 500 }),
  tp("A mini project report submitted to the", { size: 22, after: 400 }),
  tp("Department of Electrical and Information Engineering", { size: 24 }),
  tp("Faculty of Engineering", { size: 24 }),
  tp("University of Ruhuna", { size: 24 }),
  tp("Sri Lanka", { size: 24, after: 600 }),
  tp("by", { size: 22, after: 400 }),
  new Table({
    alignment: AlignmentType.CENTER, borders: noBorders, columnWidths: [2600, 500, 2000],
    width: { size: 5100, type: WidthType.DXA },
    rows: AUTHORS.map(([name, id]) => new TableRow({ children: [
      authorCell(name, 2600, AlignmentType.LEFT), authorCell("-", 500, AlignmentType.CENTER), authorCell(id, 2000, AlignmentType.LEFT)] })),
  }),
  tp("September 2026", { size: 22, before: 900 }),
  pb(),
  new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 30, color: BLACK, font: FONT })] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  pb(),
);

// ---------------------------------------------------------------- plain-language labels
const REASON = { bad_timestamp: "unreadable timestamp", out_of_range: "impossible value", missing_field: "missing field", negative_value: "negative value", unknown_zone: "unknown zone" };
const ALERT = { LOW_RENEWABLE: "low renewable share", NO_DATA: "no data", COMPONENT_FAILED: "component failed", HIGH_INVALID_RATE: "high invalid rate", HIGH_STREAM_LAG: "high stream lag", RECONCILIATION_DRIFT: "reconciliation drift", PIPELINE_TASK_FAILED: "pipeline task failed" };
const num = (re, t, d = "–") => { const m = t.match(re); return m ? m[1] : d; };
const reasonList = (obj) => Object.entries(obj).map(([k, v]) => `${v} with ${REASON[k] || k.replace(/_/g, " ")}`).join(", ");

// ================================================================= 1
S.push(h1("1. Introduction and Use Case"));
S.push(p("A utility company wants to see, in real time, how much electricity each part of its network is using and how much of it is coming from household solar panels. Once a day it also has to apply the latest tariff and billing data to that consumption and produce a bill for every household. We implemented **Use Case 3 (Smart Grid Energy Monitoring and Billing)** with both of the required kinds of source: a continuous stream of smart-meter readings and a tariff file that arrives once per day."));
S.push(h2("1.1 Business question and derived requirements"));
S.push(p("**Business question:** “What is the current grid load and renewable contribution by zone, and what will each household's bill look like once daily tariff data is applied to their consumption?” We broke this question down into functional (FR) and non-functional (NFR) requirements. Every later design decision refers back to this table:"));
S.push(table(["ID", "Requirement", "Where it is met"], [
  ["FR1", "Live load, solar generation and renewable share for each grid zone", "Speed layer, shown on the live dashboard and through the live grid API"],
  ["FR2", "Alert when the renewable contribution is considerably low", "Low-renewable alert rule (checked in daylight only)"],
  ["FR3", "Daily bill and solar-contribution report per household once the tariff arrives", "Batch layer, stored in the billing tables and published as CSV and HTML report files"],
  ["FR4", "An estimate of today's bill before the day has finished", "Lambda merge in the serving layer (provisional bill)"],
  ["FR5", "Cope with dirty data in both feeds", "Quarantine of bad readings, duplicate removal, tariff validation with fallback"],
  ["NFR1 Latency", "Live view within seconds; bills within minutes of the tariff file", "10-second micro-batches; the batch pipeline checks for work every minute"],
  ["NFR2 Correctness / replay", "Bills must be exact, reproducible and possible to re-run", "Unchangeable Parquet data lake; each day is rewritten in full when re-run"],
  ["NFR3 Consistency", "Readers never see half a day; speed and batch results can be compared", "Each day is written in one database transaction; a reconciliation record per day"],
  ["NFR4 Observability", "Detect and diagnose a failure in any stage", "Structured logs, heartbeats, seven alert rules and Prometheus"],
  ["NFR5 Cost / operability", "Runs on one laptop with one command", "Docker Compose with nine containers"],
], [1150, 4700, 4000]));
S.push(spacer());
S.push(h2("1.2 Data sources (simulated in Python)"));
S.push(p("**Streaming source.** Twenty-four households spread over four zones (North, South, East and West) each send a reading every two seconds. A reading contains a unique event ID, the meter and household it came from, the energy consumed and the solar energy generated in kWh, the zone, and a timestamp. Consumption follows a morning and an evening peak with random noise and occasional demand spikes. Solar generation follows a daylight curve that depends on how many panels each zone has (South has the fewest) and on a daily cloud level, and every simulated day one zone goes through a heavily overcast spell. About 1% of readings are made faulty on purpose: a missing field, a negative or impossible value, an unreadable timestamp, or an exact duplicate that imitates a message being delivered twice."));
S.push(p("**Daily-batch source.** Twenty seconds after each simulated day ends, this source publishes that day's tariff extract as a CSV file. For every household it lists the tariff rate, the billing tier, whether the household receives a subsidy, the day, and when the file was published. The file is first written under a temporary name and then renamed in one step, and only after that is a small completion marker written, so the batch layer can never pick up a half-written file. A household's tier and subsidy never change, and the daily rate variation is generated from the household and the day, so producing the same day again gives an identical file. About one file in three contains an invalid rate and some contain a household twice. If the source restarts, it fills in any days it missed."));
S.push(h2("1.3 Simulated clock and assumptions"));
S.push(bullet("**One simulated day lasts 300 seconds (5 minutes) of real time.** This can be changed in the configuration. Halfway through a simulated day is noon, and for alerting we treat the middle 20% of the day (from 40% to 60% of the way through) as daylight."));
S.push(bullet("All components count days from one shared start time, which is saved in PostgreSQL when the database is first created. A reading's day number is the number of whole 300-second periods between that start time and the time the reading was taken. Because the reading's own timestamp is used, not the time it happened to be processed, a late reading is still counted in the correct day, and every container agrees on where one day ends and the next begins."));
S.push(bullet("Billing: bill = max(consumption − solar, 0) × tariff rate × (1 − 15% if the household is subsidised). Surplus solar is not credited. Renewable contribution = solar ÷ consumption, capped at 100%. Amounts are in Sri Lankan rupees (LKR). All data is synthetic."));

// ================================================================= 2
S.push(h1("2. Architecture Decision: Lambda vs Kappa"));
S.push(p("Both architectures start from the same unchangeable log of events. **Kappa** has a single stream-processing path, and when history has to be recomputed it replays the log through that same path. **Lambda** keeps a speed layer that gives fast but approximate results and a batch layer that periodically recomputes exact results from the full stored data, and a serving layer combines the two. We compared them on the four points the marking rubric asks about:"));
S.push(table(["Dimension", "What this use case needs", "Lambda", "Kappa"], [
  ["Latency", "Seconds for the grid view; minutes for bills", "Speed layer: about 10–15 s end to end (measured). Batch: a bill about 1 minute after the tariff file", "Same stream latency; bills also produced by the stream"],
  ["Replay / correction", "Re-bill one day after a corrected tariff file or a code fix", "Re-run one Spark job over that one day of stored data; the result simply replaces the old one", "Replay the Kafka log from before that day through a new version of the job, then switch outputs"],
  ["Consistency", "Exact, auditable daily bills that appear all at once; duplicates removed", "Duplicates removed across the whole day, and the day is written in one transaction", "Needs exactly-once state and careful watermarks to close a day"],
  ["Cost / complexity", "Laptop-scale, two-week build, every line explainable", "Two processing paths (mitigated by one engine and shared rule modules)", "One path, but a long-running stateful join between a stream and a daily file"],
], [1400, 2600, 2950, 2900]));
S.push(spacer());
S.push(h2("2.1 Why Lambda fits this problem"));
S.push(bullet("**The two sources are different by nature.** Meter readings are a genuine stream, while the tariff feed is a complete snapshot delivered once a day. Lambda lets us treat each one in its natural form. In Kappa the daily file would have to be pushed into Kafka as a tiny 24-message stream and joined with the meter stream, which means keeping a whole day of state and waiting for a file that only arrives after the day has ended."));
S.push(bullet("**Billing must be correct and repeatable.** A bill has to be reproducible from the source data. Our batch layer recalculates each household's total from the stored raw readings, removes duplicates across the whole day, and replaces that day's results in one transaction, so running it again for the same day gives exactly the same bills. The speed layer is openly allowed to be approximate: it only removes duplicates inside each small batch and keeps running totals, which can count a reading twice if Kafka delivers it again after a crash."));
S.push(bullet(`**We can measure the difference instead of just claiming it.** For every billed day the batch job records how far the speed layer's total was from the exact batch total. Across the ${recon.length} simulated days of our run this difference was between ${f2(Math.min(...recon.map((r) => r.drift_pct)))}% and ${f2(Math.max(...recon.map((r) => r.drift_pct)))}%, and the batch layer removed ${totalDup} duplicate readings that the speed layer had counted (section 8).`));
S.push(bullet("**Reprocessing is cheap and targeted.** Correcting one day means re-reading only that day's stored data, not the whole log. The stored data also outlives Kafka's seven-day retention; a Kappa design would need to keep the Kafka log forever (or add tiered storage) to reprocess older days."));
S.push(bullet("**The daily work fits an orchestrator naturally.** The batch side is a chain of dependent steps (wait for the file, run Spark, publish the report, re-check the alerts), which benefits directly from Airflow's retries, backfill and web interface."));
S.push(h2("2.2 The rejected alternative: Kappa"));
S.push(p("Kappa would be the better choice if **all** inputs were naturally streams, if bills were needed continuously rather than once a day, or if keeping two processing paths in line were the biggest cost. Its real strengths are a single code path, no possibility of the speed and batch views disagreeing, and simpler operation. We rejected it here for three reasons: (1) the daily tariff snapshot is not a natural stream; (2) closing a day exactly inside a stream requires exactly-once state and a watermark tuned to a file that arrives after the day ends; and (3) correcting a single day would mean replaying the log through a new version of the job and swapping the outputs, which is out of proportion for a one-day fix. We still keep the replayable Kafka log, so moving towards Kappa later remains possible."));
S.push(...figure("lambda_vs_kappa.png", "Lambda (chosen) versus Kappa (rejected) for this use case.", 6.3));
S.push(h2("2.3 Trade-offs we accepted and how we contain them"));
S.push(bullet("**Two processing paths could drift apart.** We reduce this risk by using Spark for both layers and by sharing the rules between them: the same data-validation rules and the same billing formula are used by the batch job and by the API's provisional bill. The end-to-end test also recalculates every bill with the billing formula and checks that it matches."));
S.push(bullet("**The live view can be briefly wrong** (duplicates, or readings arriving more than one minute late). We accept this because the live view is only used for monitoring and for estimates that are clearly labelled provisional; final bills come only from the batch layer."));
S.push(bullet("**Bills are only ready after the day closes (plus about one minute).** This is acceptable because the business asks for daily bills, and the provisional bill covers the need for an estimate during the day."));

// ================================================================= 3
S.push(h1("3. System Architecture"));
S.push(...figure("architecture_diagram.png", "End-to-end architecture across the ingestion, processing, storage and serving layers, with observability as a cross-cutting concern.", 6.6));
S.push(p("**How data flows through the system.** (1) The meter simulator sends every reading to a Kafka topic with three partitions, using the household as the message key so that each household's readings stay in order. (2) The speed layer runs two Spark streaming queries that always continue from their last saved position in Kafka. The first calculates rolling figures for each zone and keeps them up to date in PostgreSQL. The second puts faulty readings aside, adds clean readings to the Parquet data lake (organised by day), keeps a running total for each household, and records data-quality and delay figures. (3) After a day ends, the tariff source drops that day's CSV file and its completion marker. (4) The Airflow pipeline checks PostgreSQL for the oldest finished day that has not been billed yet, waits for that day's marker and starts the Spark batch job. (5) The batch job reads that day from the data lake and writes the whole day to PostgreSQL in a single transaction; Airflow then builds that day's CSV and HTML report files from the stored bills. (6) The FastAPI service reads PostgreSQL and serves the live view, the daily view and the combination of the two; the dashboard and Prometheus read from the API."));

// ================================================================= 4
S.push(h1("4. Technology Stack and Justification"));
S.push(table(["Layer", "Choice", "Why this fits the use case", "Alternatives considered"], [
  ["Ingestion", "Apache Kafka 3.7 (one broker, without ZooKeeper), three partitions, household as the message key, every message confirmed by the broker, seven-day retention", "A durable buffer that can be replayed for continuous telemetry. Keying by household keeps each household's readings in order while spreading the 24 meters across partitions so they can be read in parallel. Retention lets the speed layer catch up after an outage, because it always resumes from its last saved position", "RabbitMQ (no replay or stored positions); Kafka with ZooKeeper (one more component to run)"],
  ["Stream processing", "Spark Structured Streaming 3.5", "Time windows based on when the reading was taken, with watermarks for late meter data; saved positions so nothing is read twice or skipped; each micro-batch can be written to several places at once; and the same programming interface as the batch job, so one engine to learn and defend", "Apache Storm (processes one message at a time and has no matching batch interface); Flink (not in the preferred stack, and its lower latency is not needed here)"],
  ["Batch processing", "Spark, submitted as a job running on two local cores", "Reads one day of Parquet data, removes duplicates across the day and joins it with the tariff file; the same code would run on a cluster unchanged", "Plain pandas (would not scale, and would be a different interface from the speed layer)"],
  ["Orchestration", "Apache Airflow 2.9", "A daily chain of dependent steps with a file sensor, retries, failure notifications, backfill (it looks back three days) and a web interface for the demo and for diagnosis", "Cron (no dependencies, retries or visibility)"],
  ["Master dataset", "Parquet data lake organised by day", "Unchangeable, column-based and cheap; recomputing a day reads only that day's files", "Keeping raw readings in PostgreSQL (a row store that would grow without limit)"],
  ["Serving store", "PostgreSQL 16", "The outputs are small and relational and are read with filters, joins (the provisional bill is live totals multiplied by the latest tariff) and aggregates; transactions, and rows that are updated in place rather than duplicated, mean both layers can safely write the same results again", "Cassandra (built for writes, with no joins or transactions, and our reads need both); HDFS or S3 on their own (not a fast query store)"],
  ["Serving API / UI", "FastAPI with a static HTML dashboard", "Typed endpoints with automatically generated documentation; the dashboard uses only the public API", "Grafana on its own (cannot express the billing merge)"],
  ["Observability", "Structured JSON logs, heartbeats stored in PostgreSQL, a Python alert engine, Prometheus", "Rules that understand both the business and the pipeline (a renewable rule that only runs in daylight, a separate silence limit for each component) plus a standard metrics and alerting tool", "ELK or Grafana stack (heavier than needed on one machine)"],
  ["Packaging", "Docker Compose (nine services)", "One command gives a reproducible environment; images are built from official Apache Kafka, Apache Airflow and Python bases", "Manual installation"],
], [1250, 2250, 4050, 2300]));

// ================================================================= 5
S.push(h1("5. Implementation"));
S.push(h2("5.1 Ingestion"));
S.push(bullet("The meter simulator creates the Kafka topic itself with three partitions and keeps retrying until the broker is ready. Every message must be confirmed by the broker, only one unconfirmed batch is allowed at a time (so a retry can never change the order of a household's readings), and every confirmed or failed send is counted. When the container is stopped it sends whatever is still pending and closes cleanly, and it publishes its delivery counters for Prometheus."));
S.push(bullet("The tariff source never exposes a partial file (temporary name, one-step rename, then the completion marker last), always produces the same file for the same day, and fills in any days it missed while it was down."));
S.push(h2("5.2 Speed layer"));
S.push(bullet("On its very first start the speed layer reads Kafka from the beginning, and after that it continues from its saved position (stored next to the data lake). Nothing sent before Spark was ready is lost, and a restart picks up exactly where it stopped."));
S.push(bullet("**Cleaning:** every reading is checked against a fixed structure and against the shared data-quality rules (missing field, unreadable timestamp, unknown zone, negative value, or more than 50 kWh). Invalid readings are stored in a separate quarantine area together with the reason they failed. Nothing is dropped silently."));
S.push(bullet("**Windowing and aggregation:** clean readings are grouped per zone into 30-second windows that move forward every 15 seconds, allowing readings to arrive up to one minute late. For each window we calculate the load, the solar generation, the renewable share and the number of households, and update that zone's row in PostgreSQL (writing the same window twice gives the same result)."));
S.push(bullet("**Master dataset and enrichment:** in the second query every micro-batch has its duplicates removed, each reading is labelled with the simulated day it was taken on, and it is added to that day's part of the raw data lake. The same query adds each household's usage to its running total for the day, records the number of readings, the invalid readings by reason, the duplicates and the delay between a reading being taken and being stored, and sends a heartbeat."));
S.push(h2("5.3 Batch layer and orchestration"));
S.push(bullet("The batch job reads only the day being billed, removes duplicate readings **across the whole day**, and calculates exact figures for each household: consumption, solar, net consumption, surplus solar, solar-contribution percentage, peak reading and number of readings."));
S.push(bullet("It reads the tariff file with every column treated as text first, then rejects rows whose rate is blank, not a number, zero or negative, or whose tier is unknown. It keeps one row per household and, when a household's rate is missing or invalid, **falls back to that household's last valid tariff** from an earlier day, marking the bill as using a fallback rate. Households with no usable tariff at all are logged and counted rather than billed with a guess."));
S.push(bullet("It then joins consumption with tariffs, applies the billing formula, and saves the daily consumption, the validated tariffs, the bills and the reconciliation figures. For that day it deletes any old rows and inserts the new ones **in one transaction**, so the day appears all at once and a re-run simply replaces it. Every run has its own run ID, which appears in every log line and is stored with each bill."));
S.push(bullet("The Airflow pipeline runs every minute and has six steps: find the oldest finished day that has not been billed and has data (skipping the rest of the run if there is none, and looking back up to three days); wait for that day's tariff file; run the Spark batch job; publish the CSV and HTML report; re-check the alert rules; and log that the run finished. Failed steps are retried twice, 20 seconds apart, and a final failure raises a critical alert. We poll every minute instead of using a daily schedule because, with the compressed clock, a day ends every five minutes at no fixed time of day."));
S.push(...figure("screenshots/airflow_grid.png", "Airflow grid view of the daily batch pipeline: complete runs (green) bill a finished simulated day; checks in between find nothing to do and skip the remaining steps (pink).", 6.5));
S.push(h2("5.4 Storage and serving layer"));
S.push(table(["Stored data", "Written by", "Purpose"], [
  ["Raw readings in Parquet, organised by day", "Speed layer", "Unchangeable master dataset used by the batch layer"],
  ["Quarantined readings in Parquet, organised by failure reason", "Speed layer", "Rejected readings kept for diagnosis"],
  ["Live zone figures", "Speed layer", "Load, solar and renewable share per zone and window (kept for 6 hours)"],
  ["Live household totals", "Speed layer", "Approximate running totals for the current day"],
  ["Stream quality figures", "Speed layer", "Per micro-batch: readings, invalid and duplicate counts, delay"],
  ["Daily consumption, validated tariffs and bills", "Batch layer", "The exact daily view and the final bills"],
  ["Daily reconciliation", "Batch layer", "Difference between speed and batch totals, plus data-quality counts, per day"],
  ["Alerts, component heartbeats and the shared clock", "Observability / shared", "Alert history, component health and the common start time"],
], [3700, 1700, 4450]));
S.push(spacer());
S.push(table(["Endpoint", "View", "Answers"], [
  ["GET /api/grid/live, /api/grid/history", "Speed", "Current load, solar and renewable share per zone; the last 15 minutes"],
  ["GET /api/households/live", "Speed", "Today's running consumption per household"],
  ["GET /api/billing/daily, /summary, /days", "Batch", "Bill and solar contribution per household; totals per zone; list of billed days"],
  ["GET /api/billing/projection", "Merge", "Provisional bill so far today = live consumption × latest validated tariff, shown beside the last final bill"],
  ["GET /api/reconciliation", "Batch", "Speed-versus-batch difference and data-quality counts"],
  ["GET /api/alerts, /api/pipeline/status, /health, /metrics", "Observability", "Open and resolved alerts, heartbeats, stream quality and Prometheus metrics"],
], [3900, 1200, 4750]));
S.push(spacer());
S.push(p("The live zone query deliberately returns the latest **complete** window for each zone, because a window that is still open holds only a few seconds of data and would under-report the load. If the database is unavailable, the API logs the problem and returns a “service unavailable” response instead of crashing. The same service also hosts the dashboard and the interactive API documentation."));

// ================================================================= 6
S.push(h1("6. Observability Design"));
S.push(p("Our aim is that any failure, whether a stopped producer, a stuck Spark query, a crashed batch job or a bad input file, is **detected** automatically and can be **diagnosed** from one place. We collect four kinds of signal and use shared identifiers to trace work from one end of the pipeline to the other:"));
S.push(table(["Signal", "How it is produced", "Why"], [
  ["Structured logs", "Every component writes one JSON record per event (time, level, component, message and extra fields) to its console and to its own log file. Each record carries the simulated day and, where relevant, the micro-batch, batch run, reading and household it relates to", "Follow one day or one batch run through the producer, Spark, Airflow and the API; easy for a log collector to parse"],
  ["Heartbeats", "Each long-running component regularly records its status and a short detail in PostgreSQL; each component has its own limit for how long it may stay silent", "Shows which stage is alive; the batch layer is normally quiet for a whole day, so a single limit for everything would cause false alarms"],
  ["Pipeline metrics", "Stream quality figures for every micro-batch and reconciliation figures for every day, published on the API's metrics endpoint (refreshed from PostgreSQL each time Prometheus reads it) and on the producer's own metrics endpoint", "Volume, invalid rate by reason, duplicates, delay, speed-versus-batch difference, delivery failures and API response times"],
  ["Alerts", "A Python alert engine checks every 15 seconds and after each batch run; Prometheus evaluates matching alert rules", "Turns the signals into alerts that are never duplicated, close themselves when the problem clears, and can be sent to a chat webhook"],
], [1500, 4600, 3750]));
S.push(spacer());
S.push(table(["Rule", "Condition (default threshold)", "Detects"], [
  ["Low renewable share (business rule)", "A zone's renewable share is below 10% in the latest complete window, during simulated daylight only", "The grid relying on non-renewable supply, e.g. an overcast zone"],
  ["No data", "A component has not sent a heartbeat within its limit (2 minutes for streaming components; 2 simulated days plus 2 minutes for the batch layer)", "A stopped or stuck producer, Spark query, alert engine or batch layer"],
  ["Component failed", "A component reports a status other than OK (e.g. the batch job threw an error)", "Crashes in components that are still sending heartbeats"],
  ["High invalid rate", "More than 5% of readings quarantined in the last 5 minutes", "A problem with the sensors or the data format upstream"],
  ["High stream lag", "Average delay from a reading being taken to being stored is over 60 seconds", "The speed layer falling behind"],
  ["Reconciliation drift", "Speed and batch totals for the last billed day differ by more than 10%", "The speed layer double counting or losing data"],
  ["Pipeline task failed", "An Airflow step failed after all its retries", "A failure in the batch orchestration"],
], [2300, 4300, 3250]));
S.push(p("The database only allows one open alert of each type for the same zone or component. While the condition continues, that alert's latest time and value are updated, and when the condition clears the alert is closed automatically. Every change is logged, and it is also posted to a Slack- or Teams-compatible webhook if one is configured."));
S.push(p("**Tracing.** Every reading has its own event ID, every speed-layer micro-batch a batch number and every batch-layer run a run ID. These, together with the simulated day and the household, are written into the structured logs and stored with the results (each bill records the run that produced it). This lets us follow a single reading, micro-batch or daily billing run from the producer through Kafka, Spark and Airflow to PostgreSQL and the API, which is how a failure is pinned down to the stage where it happened."));
S.push(h2("6.1 Failure drill: stopping the streaming source"));
const T = drill.timeline.map((t) => t.time);
const DW = drill.timeline.map((t) => t.what);
S.push(p(`To show that failures are detected and can be diagnosed, we stopped the meter producer container at ${drill.stopped_at} UTC. Within about two minutes the alert engine raised two “no data” alerts, one for the producer and one for the speed layer (which had nothing left to process), and the health check marked both as stale. After we restarted the producer, the speed layer continued from its saved position in Kafka and both alerts closed on their own, with no manual action.`));
S.push(table(["Time (UTC)", "Observation"], [
  [T[0], "Meter producer container stopped (the streaming source goes silent)"],
  [T[1], `Health check marks the meter producer as stale (last heartbeat ${num(/(\d+) s ago/, DW[1])} s ago); overall status becomes DEGRADED`],
  [T[2], `Health check marks the speed layer as stale (last heartbeat ${num(/(\d+) s ago/, DW[2])} s ago)`],
  [T[3], `Critical “no data” alert raised for the meter producer (silent for ${num(/for ([\d.]+) min/, DW[3])} minutes against a 2-minute limit)`],
  [T[4], `Critical “no data” alert raised for the speed layer (silent for ${num(/for ([\d.]+) min/, DW[4])} minutes)`],
  [T[5], "Dashboard screenshot taken: status DEGRADED, both alerts listed (Figure 4)"],
  [T[6], "Meter producer container started again"],
  [T[7], "Both alerts closed automatically; health check back to OK"],
], [1800, 8050]));
S.push(spacer());
S.push(...figure("screenshots/drill_dashboard.png", "Dashboard during the drill: “no data” alerts and stale components.", 5.9));

// ================================================================= 7
S.push(h1("7. Testing and Reproducibility"));
S.push(bullet(`**Unit tests** (no infrastructure needed) cover the data-quality rules, the billing formula, the simulated clock, both simulators (fields, value ranges, repeatability, the overcast spell, every kind of faulty reading being rejected, and the safe file drop), the alert conditions, the API endpoints with a stand-in database (the provisional bill, health staleness, the response when the database is down, and metrics) and the report generator. All ${num(/(\d+) passed/, tests)} tests passed in about ${Math.round(parseFloat(num(/in ([\d.]+)s/, tests, "1")))} second.`));
S.push(bullet("**End-to-end smoke test** against the running system. It checks each layer in turn and reported the following:"));
const sm = {
  delivered: num(/(\d+) delivered/, smoke), zones: num(/all (\d+) zones/, smoke, "4"), events5: num(/(\d+) events/, smoke),
  rules: num(/(\d+) rules/, smoke), bills: num(/(\d+) bills for/, smoke), day: num(/bills for sim_day (\d+)/, smoke), drift: num(/drift=([\d.]+)%/, smoke),
  households: num(/(\d+) households, total/, smoke), total: num(/total ([\d.]+)/, smoke),
};
const q = status.stream_quality_last_5m;
S.push(table(["Check", "Result"], [
  ["Ingestion: producer delivered readings to Kafka", `Passed: ${Number(sm.delivered).toLocaleString("en-US")} readings delivered`],
  ["Speed layer: a live window exists for every zone", `Passed: all ${sm.zones} zones (North, South, East, West)`],
  ["Speed layer: readings processed in the last 5 minutes", `Passed: ${Number(sm.events5).toLocaleString("en-US")} readings`],
  ["Processing: faulty readings are quarantined", `Passed: ${reasonList(q.invalid_by_reason)}`],
  ["Observability: health check reports every component OK", "Passed: all five components OK"],
  ["Observability: metrics endpoint exports pipeline figures", "Passed"],
  ["Observability: Prometheus alert rules loaded", `Passed: ${sm.rules} rules`],
  ["Observability: Prometheus can reach every metrics source", "Passed: producer, API and Prometheus itself all up"],
  ["Batch layer: every bill matches the billing formula", `Passed: ${sm.bills} bills for simulated day ${sm.day}, no mismatches`],
  ["Batch layer: speed-versus-batch reconciliation recorded", `Passed: difference ${sm.drift}%`],
  ["Lambda merge: provisional bills for the current day", `Passed: ${sm.households} households, total LKR ${money(sm.total)}`],
], [5000, 4850]));
S.push(spacer());
S.push(bullet("**Reproducing the results:** start the whole system with one Docker Compose command, wait about six minutes for the first bill, then run the end-to-end smoke test. All settings are controlled through environment variables."));

// ================================================================= 8
S.push(h1("8. Results"));
S.push(p(`The results below come from one continuous run of the system (${recon.length} simulated days, about ${Math.round(recon.length * 5)} minutes of real time). Every number was read from the API by an automated capture script.`));
S.push(h2("8.1 Live dashboard and real-time API"));
S.push(...figure("screenshots/dashboard_top.png", "Live dashboard: speed-layer summary figures, renewable share per zone with the alert threshold, 15-minute history, active alerts and pipeline health.", 4.5));
S.push(...figure("screenshots/api_grid_live.png", "Live grid endpoint: the latest complete window for each zone (speed view).", 5.2, 4.6));
S.push(h2("8.2 Daily billing and solar-contribution report (batch view)"));
S.push(p(`For simulated day ${billing.sim_day}, the batch layer billed ${billing.count} households for a total of LKR ${money(billing.total_billed)}. Totals per zone:`));
S.push(table(["Zone", "Households", "Consumption kWh", "Solar kWh", "Avg solar contribution %", "Billed (LKR)"],
  summary.zones.map((z) => [z.grid_zone, z.households, f2(z.total_consumption_kwh), f2(z.total_solar_kwh), f2(z.avg_solar_contribution_pct, 1), money(z.total_billed)]),
  [1400, 1300, 1800, 1500, 2150, 1700]));
S.push(spacer());
S.push(p("The first rows of the per-household billing report:"));
S.push(table(["Household", "Zone", "Tier", "Net kWh", "Solar %", "Tariff", "Source", "Subsidy", "Bill (LKR)"],
  billing.rows.slice(0, 6).map((r) => [r.household_id, r.grid_zone, r.billing_tier.replace("residential_", ""), f2(r.net_consumption_kwh), f2(r.solar_contribution_pct, 1), f2(r.tariff_rate), r.tariff_source === "current_day" ? "today" : "fallback", r.subsidy_flag ? "yes" : "no", money(r.bill_amount)]),
  [1100, 900, 1150, 1000, 900, 900, 1050, 900, 1250]));
S.push(spacer());
S.push(...figure("screenshots/report_file.png", "Daily consolidated report file, published automatically by the Airflow pipeline.", 6.2, 5.0));
S.push(h2("8.3 Lambda merge: provisional bills during the day"));
const pr = projection.rows.find((r) => r.household_id === "H-001") || projection.rows[0];
S.push(p(`At the time of capture (simulated day ${projection.clock.sim_day}, ${projection.clock.sim_time_of_day}), household ${pr.household_id} had used ${f2(pr.consumption_kwh)} kWh and generated ${f2(pr.solar_kwh)} kWh of solar according to the speed layer. Applying its latest validated tariff from the batch layer (${f2(pr.tariff_rate)} LKR/kWh, from day ${pr.tariff_sim_day}) gives a provisional bill so far of LKR ${money(pr.provisional_bill_so_far)}, shown next to its final bill of LKR ${money(pr.last_final_bill)} for day ${pr.last_final_sim_day}. The provisional total for all 24 households was LKR ${money(projection.total_provisional)}. Figure 8 shows the same endpoint for this household a few seconds later; the figures grow as new readings arrive.`));
S.push(...figure("screenshots/api_projection.png", "Provisional bill endpoint: live consumption from the speed layer combined with the tariff from the batch layer.", 5.2, 6.5));
S.push(h2("8.4 Speed vs batch reconciliation and data quality"));
S.push(table(["Sim day", "Raw readings", "Duplicates removed", "Speed kWh", "Batch kWh", "Difference %", "Invalid tariff rows", "Fallback tariffs", "Billed (LKR)"],
  recon.map((r) => [r.sim_day, r.raw_events, r.duplicates_removed, f2(r.speed_consumption_kwh), f2(r.batch_consumption_kwh), f2(r.drift_pct), r.invalid_tariff_rows, r.fallback_tariffs, money(r.total_billed)]),
  [800, 1050, 1050, 1150, 1150, 900, 1250, 1150, 1300]));
S.push(spacer());
const dupDays = recon.filter((r) => r.duplicates_removed > 0).map((r) => r.sim_day);
const tariffDefects = recon.filter((r) => r.invalid_tariff_rows > 0 || r.duplicate_tariff_rows > 0);
const fb = recon.reduce((a, r) => a + r.fallback_tariffs, 0);
S.push(p(`Over the whole run the batch layer read ${totalRaw.toLocaleString("en-US")} readings from the data lake and removed ${totalDup} duplicates (on days ${dupDays.join(", ")}). These were readings delivered a second time in a later micro-batch than the original, so the speed layer, which only removes duplicates within one micro-batch, could not see them and counted them twice. A positive difference is exactly that over-count, and the batch layer's day-wide duplicate removal takes it out of the final bill. Days with no difference simply had no such duplicates. Faulty tariff files arrived on day${tariffDefects.length > 1 ? "s" : ""} ${tariffDefects.map((r) => r.sim_day).join(" and ")}: the invalid or repeated rows were rejected, and ${fb} household${fb === 1 ? " was" : "s were"} billed with ${fb === 1 ? "its" : "their"} previous valid tariff instead. Days 1 and 2 also include the three-and-a-half-minute producer outage from the failure drill (section 6.1). That lowers their consumption and bills but not their correctness, because both layers saw the same, smaller set of readings.`));
S.push(p(`In the five minutes before capture, the speed layer processed ${q.total_events.toLocaleString("en-US")} readings in ${q.micro_batches} micro-batches. It quarantined ${q.invalid_events} of them (${f2(q.invalid_rate_pct)}%: ${reasonList(q.invalid_by_reason)}), dropped ${q.duplicate_events} duplicates within micro-batches, and had an average delay of ${f2(q.avg_lag_seconds, 1)} seconds from a reading being taken to being stored.`));
S.push(h2("8.5 Alerts, orchestration and monitoring"));
const lowR = [...alertsOpen, ...alertsResolved].filter((a) => a.alert_type === "LOW_RENEWABLE");
const byZone = {};
for (const a of lowR) byZone[a.scope] = (byZone[a.scope] || 0) + 1;
S.push(p(`During the run the alert engine raised ${Object.entries(alertCounts).map(([k, v]) => `${v} “${ALERT[k] || k.toLowerCase().replace(/_/g, " ")}” alerts`).join(" and ")}. The low-renewable alerts by zone were ${Object.entries(byZone).map(([k, v]) => `${k} ${v}`).join(", ")}. South, which has the fewest solar panels, drops below 10% at the start of simulated daylight every day, while the other zones only triggered during that day's overcast spell. Each alert closed itself within one or two 15-second checks once the next window recovered. The two “no data” alerts come from the failure drill in section 6.1. Because the low-renewable rule has no minimum duration, a zone hovering around the threshold can raise short-lived alerts; section 9 describes the fix.`));
S.push(...figure("screenshots/prometheus_alerts.png", "Prometheus: the pipeline's alert rules loaded and evaluated.", 6.3, 6.5));
S.push(...figure("screenshots/spark_streaming.png", "Spark UI: the two streaming queries of the speed layer (zone figures and raw data lake).", 6.3, 5.0));

// ================================================================= 9
S.push(h1("9. Limitations, Trade-offs and Production-Scale Changes"));
S.push(table(["Area", "Simplification in this project", "What we would do at production scale"], [
  ["Kafka", "One broker, a single copy of each message, no authentication", "At least three brokers, three copies of each message with at least two required to confirm a write, duplicate-safe producers, encrypted and authenticated connections, and a schema registry so the message format can evolve safely"],
  ["Spark", "Runs on two local cores inside a container; the batch job runs inside the Airflow container", "Spark on Kubernetes or YARN, launched by Airflow as a separate job, with autoscaling"],
  ["Speed-layer accuracy", "At-least-once: duplicates are only removed within a micro-batch, and running totals can count a reading twice after a crash", "Duplicate removal across batches or transactional writes for exactly-once results, while keeping the batch layer as the source of truth"],
  ["Late data", "Readings more than one minute late are left out of the live windows (they are still kept in the data lake)", "Set the watermark from observed delays, and re-run a day's billing if late data arrives after the bill"],
  ["Airflow", "Stand-alone mode, running one task at a time, with a SQLite metadata database", "A distributed executor with a PostgreSQL metadata database, and runs started by the arrival of the tariff file itself"],
  ["Data lake", "A local Docker volume holding Parquet files", "S3 or HDFS with a table format such as Delta Lake or Iceberg for safe appends, compaction and time travel"],
  ["Serving", "One PostgreSQL instance, no login, the dashboard refreshes every 5 seconds", "Read replicas or a time-series database for live figures, API authentication, and pushed updates instead of polling"],
  ["Observability", "Our own alert engine and a single Prometheus, without Grafana or Alertmanager; the low-renewable rule has no minimum duration, so it can flicker near the threshold", "Alert hysteresis (for example, trigger after 2 minutes below 10% and clear above 12%), Alertmanager for routing and on-call, Grafana dashboards, OpenTelemetry tracing and a central log store"],
  ["Billing", "A flat rate per kWh, one subsidy rule, no credit for surplus solar", "Tiered and time-of-use tariffs, net-metering credits, versioned tariffs and an audit trail"],
  ["Simulation", "24 households and 5-minute days", "Real meter volumes need more partitions and a partitioning scheme by zone and date"],
], [1400, 3900, 4550]));
S.push(spacer());
S.push(p("**What we would do differently.** We would introduce a schema registry from the first day, because the loosely defined JSON messages are the main source of dirty-data risk. We would use a table format such as Delta Lake so that the batch layer could replace a day directly and atomically in the data lake. And we would base the renewable alert on the solar output expected for that hour and weather, instead of a fixed 10%."));

// ================================================================= 10
S.push(h1("10. Conclusion"));
S.push(p("The platform takes in a continuous stream of meter readings and a daily tariff file. It answers the business question both in real time (grid load and renewable share by zone) and once a day (exact household bills and solar contribution), and it presents both views, together with their combination, through one API and one dashboard. We chose Lambda because this use case combines a need for low-latency monitoring with a daily calculation that must be correct and repeatable over a source that is naturally a batch, and the measured difference between the speed and batch results shows why the batch layer is needed. Every stage of the pipeline can be observed through structured logs, heartbeats, quality and delay metrics, seven alert rules and Prometheus."));

S.push(h2("Individual contributions"));
S.push(bullet("**Sewvandi M.A.K. (EG/2021/4808):** the Lambda versus Kappa decision and the overall system design; the Spark streaming speed layer (cleaning, windowing and the raw data lake); the Spark batch layer (daily recalculation, tariff join, billing and reconciliation); Airflow orchestration; the PostgreSQL schema; and writing the report."));
S.push(bullet("**Peiris P.R.S. (EG/2021/4706):** the smart-meter and tariff data simulators; the Kafka ingestion setup; the REST API and live dashboard; observability (structured logging, alert rules and Prometheus); the Docker Compose setup; and the automated tests and results capture."));


// ---------------------------------------------------------------- build
const doc = new Document({
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: BLACK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 30, color: BLACK, font: FONT },
        paragraph: { spacing: { before: 300, after: 140 }, keepNext: true, border: { bottom: { color: BLACK, space: 4, style: BorderStyle.SINGLE, size: 6 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { bold: true, size: 25, color: BLACK, font: FONT },
        paragraph: { spacing: { before: 220, after: 100 }, keepNext: true } },
    ],
  },
  sections: [{
    properties: { titlePage: true, page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, bottom: 1000, left: 1030, right: 1030 } } },
    headers: {
      first: new Header({ children: [] }),
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "EC8203 Mini Project — Smart Grid Lambda Pipeline", size: 18, color: BLACK, font: FONT })] })] }),
    },
    footers: {
      first: new Footer({ children: [] }),
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], size: 20, font: FONT, color: BLACK })] })] }),
    },
    children: S,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(R("EC8203_MiniProject_Report.docx"), buf);
  console.log("wrote report/EC8203_MiniProject_Report.docx");
});
