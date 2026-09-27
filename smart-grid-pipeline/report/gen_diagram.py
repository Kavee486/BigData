"""Renders report/architecture_diagram.png (run from the repo root:
python report/gen_diagram.py). Layered view: sources -> ingestion ->
processing (speed + batch) -> storage -> serving, with observability as a
cross-cutting band."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

fig, ax = plt.subplots(figsize=(15, 9))
ax.set_xlim(0, 15)
ax.set_ylim(0, 9)
ax.axis("off")

C = {
    "source": "#2f6fed", "ingest": "#111827", "speed": "#d9822b", "batch": "#7c3aed",
    "store": "#0f8a4f", "serve": "#c73636", "obs": "#475569",
}


def box(x, y, w, h, title, body, color, fs=8.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.1",
                                linewidth=1.1, edgecolor="#111", facecolor=color, zorder=2))
    ax.text(x + w / 2, y + h - 0.22, title, ha="center", va="top", fontsize=fs + 1.2, color="white",
            weight="bold", zorder=3)
    ax.text(x + w / 2, y + h - 0.55, body, ha="center", va="top", fontsize=fs, color="white", zorder=3,
            linespacing=1.35)


def arrow(p1, p2, label=None, color="#222", rad=0.0, lx=0.0, ly=0.12, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=14, linewidth=1.5, color=color,
                                 zorder=1, linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2 + lx, (p1[1] + p2[1]) / 2 + ly, label, fontsize=7.8, ha="center",
                color="#111", zorder=4, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))


# Layer bands
layers = [(0.15, 2.45, "1  SOURCES"), (2.75, 2.35, "2  INGESTION"), (5.3, 3.35, "3  PROCESSING"),
          (8.85, 2.85, "4  STORAGE"), (11.9, 2.95, "5  SERVING")]
for x, w, name in layers:
    ax.add_patch(Rectangle((x, 1.75), w, 6.55, facecolor="#f3f4f6", edgecolor="#d1d5db", zorder=0))
    ax.text(x + w / 2, 8.12, name, ha="center", fontsize=10, weight="bold", color="#374151")

# 1 Sources
box(0.3, 5.75, 2.15, 1.75, "Smart meters", "smart_meter_producer.py\n24 households, 4 zones\n1 event / 2 s each\n~1% dirty + duplicates", C["source"])
box(0.3, 2.35, 2.15, 1.75, "Tariff extract", "tariff_batch_source.py\n1 CSV per sim-day\n(end of day + 20 s)\natomic + _SUCCESS", C["source"])

# 2 Ingestion
box(2.9, 5.75, 2.05, 1.75, "Apache Kafka", "KRaft, 1 broker\ntopic smart-meter-\nreadings, 3 partitions\nkey = household_id", C["ingest"])
box(2.9, 2.35, 2.05, 1.75, "Landing zone", "/data/batch_drop\ntariff_simdayN.csv\n_SUCCESS_simdayN", C["ingest"])

# 3 Processing
box(5.45, 5.3, 3.05, 2.55, "SPEED LAYER",
    "Spark Structured Streaming\n1. parse + validate (quality_rules)\n2. 30 s windows / 15 s slide,\n    1 min watermark, by zone\n3. dedup (micro-batch) -> lake\n4. running household totals\n5. quality + lag metrics", C["speed"], fs=8.2)
box(5.45, 3.55, 3.05, 1.2, "Apache Airflow", "daily_batch_pipeline, every 60 s:\nresolve day > sensor > spark-submit\n> report > alert check", C["batch"], fs=8.2)
box(5.45, 1.95, 3.05, 1.35, "BATCH LAYER", "Spark batch (per finished sim-day)\nglobal dedup, exact totals, tariff\nvalidate + fallback, join, bill,\nspeed-vs-batch reconciliation", C["batch"], fs=8.2)

# 4 Storage
box(9.0, 6.0, 2.55, 1.85, "Parquet data lake", "raw_meter_events/\n  sim_day=N (immutable)\nquarantine/\n  invalid_reason=...", C["store"], fs=8.2)
box(9.0, 3.2, 2.55, 2.55, "PostgreSQL", "speed: live_zone_metrics,\nlive_household_consumption,\nstream_quality_metrics\nbatch: daily_billing_report,\nhousehold_daily_consumption,\ntariff_reference, batch_recon.\nops: alerts, pipeline_health", C["store"], fs=7.9)
box(9.0, 1.95, 2.55, 1.05, "Report files", "reports/daily_report_\nsimdayN.html + .csv", C["store"], fs=8.2)

# 5 Serving
box(12.05, 5.0, 2.65, 2.85, "FastAPI", "/api/grid/live, /history\n/api/households/live\n/api/billing/daily, /summary\n/api/billing/projection\n  (speed x batch merge)\n/api/reconciliation\n/api/alerts, /health, /metrics", C["serve"], fs=8.0)
box(12.05, 1.95, 2.65, 2.7, "Dashboard", "live zones + 15 min chart\nalerts, pipeline health\nprovisional bills (merge)\ndaily billing report\nreconciliation", C["serve"], fs=8.2)

# Observability band
ax.add_patch(FancyBboxPatch((0.3, 0.1), 14.4, 1.45, boxstyle="round,pad=0.04,rounding_size=0.1",
                            facecolor=C["obs"], edgecolor="#111", zorder=2))
ax.text(7.5, 1.45, "OBSERVABILITY (cross-cutting)", ha="center", va="top", color="white", weight="bold", fontsize=10)
ax.text(7.5, 1.05, "Structured JSON logs from every stage, correlated by sim_day / batch_id / run_id / event_id   |   heartbeats -> pipeline_health\n"
        "alerts.py: LOW_RENEWABLE, NO_DATA, COMPONENT_FAILED, HIGH_INVALID_RATE, HIGH_STREAM_LAG, RECONCILIATION_DRIFT, PIPELINE_TASK_FAILED\n"
        "Prometheus scrapes API :8000/metrics + producer :8001 and evaluates alert_rules.yml   |   Spark UI :4040   |   Airflow UI :8080",
        ha="center", va="top", color="white", fontsize=7.9, linespacing=1.5)

# Flows: speed path
arrow((2.45, 6.6), (2.9, 6.6))
arrow((4.95, 6.6), (5.45, 6.6), "stream")
arrow((8.5, 7.0), (9.0, 7.0), "append")
arrow((8.5, 5.6), (9.0, 5.1), "upsert", ly=0.2)
# batch path
arrow((2.45, 3.2), (2.9, 3.2))
arrow((4.95, 3.55), (5.45, 4.05), "marker", ly=0.14)
arrow((6.95, 3.55), (6.95, 3.3))
arrow((4.95, 2.8), (5.45, 2.6), "CSV", ly=-0.28)
arrow((9.0, 6.2), (8.5, 3.2), "read sim_day=N", rad=0.35, lx=-0.35, ly=0.0, color="#5b21b6")
arrow((8.5, 2.95), (9.0, 3.45), "txn", ly=0.05, lx=-0.15)
arrow((8.5, 2.3), (9.0, 2.4), "files", ly=-0.3)
# serving
arrow((11.55, 4.6), (12.05, 5.7), "SQL", lx=-0.1)
arrow((13.35, 5.0), (13.35, 4.65), "JSON", lx=0.45, ly=-0.05)

ax.text(7.5, 8.72, "Smart Grid Energy Monitoring & Billing - Lambda Architecture", fontsize=15, weight="bold", ha="center")
ax.text(7.5, 8.42, "speed layer = fast, approximate view of now   |   batch layer = exact, replayable daily bills   |   merged at query time by the serving API",
        fontsize=9.5, ha="center", color="#444")

plt.savefig("report/architecture_diagram.png", dpi=180, bbox_inches="tight", facecolor="white")
print("saved report/architecture_diagram.png")
