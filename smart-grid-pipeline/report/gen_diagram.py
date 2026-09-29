"""Renders the report's architecture figure (report/architecture_diagram.png).
Run from the repo root: python report/gen_diagram.py

Black-and-white, report-style layered view: sources -> ingestion ->
processing (speed + batch) -> storage -> serving, with observability as a
cross-cutting band."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Times New Roman"

fig, ax = plt.subplots(figsize=(15, 9))
ax.set_xlim(0, 15)
ax.set_ylim(0, 9)
ax.axis("off")

# Grey levels distinguish the layers without colour.
FILL = {"plain": "white", "source": "#dbeafe", "ingest": "#e5e7eb", "speed": "#fde8c8", "batch": "#e9d5ff",
        "lake": "#d1fae5", "db": "#bbf7d0", "files": "#ecfccb", "serve": "#fee2e2", "obs": "#e0f2fe"}
EDGE = {"source": "#1d4ed8", "ingest": "#374151", "speed": "#c2410c", "batch": "#7e22ce", "lake": "#047857",
        "db": "#15803d", "files": "#4d7c0f", "serve": "#b91c1c", "obs": "#0369a1", "plain": "black"}


def box(x, y, w, h, title, body, fill="plain", fs=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
                                linewidth=1.6, edgecolor=EDGE[fill], facecolor=FILL[fill], zorder=2))
    ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="top", fontsize=fs + 1.5, color="black",
            weight="bold", zorder=3)
    ax.text(x + w / 2, y + h - 0.58, body, ha="center", va="top", fontsize=fs, color="black", zorder=3,
            linespacing=1.3)


def arrow(p1, p2, label=None, rad=0.0, lx=0.0, ly=0.13, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=14, linewidth=1.3, color="black",
                                 zorder=1, linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2 + lx, (p1[1] + p2[1]) / 2 + ly, label, fontsize=9.5, ha="center",
                color="black", style="italic", zorder=4,
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))


layers = [(0.15, 2.45, "Sources"), (2.75, 2.35, "Ingestion"), (5.3, 3.35, "Processing"),
          (8.85, 2.85, "Storage"), (11.9, 2.95, "Serving")]
for x, w, name in layers:
    ax.add_patch(Rectangle((x, 1.75), w, 6.55, facecolor="white", edgecolor="black", linestyle=(0, (4, 3)),
                           linewidth=0.8, zorder=0))
    ax.text(x + w / 2, 8.1, name, ha="center", fontsize=13, weight="bold", color="black")

box(0.3, 5.75, 2.15, 1.75, "Smart meters", "24 households, 4 zones\none reading every 2 s\n~1% faulty readings", "source")
box(0.3, 2.35, 2.15, 1.75, "Tariff extract", "one CSV file per\nsimulated day,\npublished after the\nday ends", "source")

box(2.9, 5.75, 2.05, 1.75, "Apache Kafka", "meter readings topic\n3 partitions\nkeyed by household", "ingest")
box(2.9, 2.35, 2.05, 1.75, "Landing area", "daily tariff file\n+ completion marker", "ingest")

box(5.45, 5.3, 3.05, 2.55, "Speed layer",
    "Spark Structured Streaming\nvalidate and clean readings\n30 s windows per zone\n(load, solar, renewable %)\narchive clean readings\nrunning household totals", "speed")
box(5.45, 3.55, 3.05, 1.2, "Apache Airflow", "schedules the daily job:\nwait for file, run Spark,\npublish report, check alerts", "batch")
box(5.45, 1.95, 3.05, 1.35, "Batch layer", "Spark batch job per day\nexact totals, tariff join,\nbills, reconciliation", "batch")

box(9.0, 6.0, 2.55, 1.85, "Parquet data lake", "raw readings\npartitioned by day\n(immutable)\nrejected readings", "lake")
box(9.0, 3.2, 2.55, 2.55, "PostgreSQL", "live zone metrics\nlive household totals\ndaily bills\nreconciliation results\nalerts and health", "db")
box(9.0, 1.95, 2.55, 1.05, "Report files", "daily CSV and\nHTML report", "files")

box(12.05, 5.0, 2.65, 2.85, "REST API", "live grid view\ndaily billing report\nprovisional bills\n(speed + batch merge)\nalerts, health,\nmetrics", "serve")
box(12.05, 1.95, 2.65, 2.7, "Dashboard", "live zone view\nalerts and health\nprovisional and\nfinal bills", "serve")

ax.add_patch(FancyBboxPatch((0.3, 0.1), 14.4, 1.45, boxstyle="round,pad=0.04,rounding_size=0.08",
                            facecolor=FILL["obs"], edgecolor=EDGE["obs"], linewidth=1.6, zorder=2))
ax.text(7.5, 1.45, "Observability (all layers)", ha="center", va="top", color="black", weight="bold", fontsize=12)
ax.text(7.5, 1.08, "structured JSON logs from every component   |   component heartbeats and health check\n"
        "alert rules: low renewable share, missing data, failed component, invalid data rate, processing lag, speed/batch drift\n"
        "Prometheus metrics and alert rules   |   Spark and Airflow monitoring interfaces",
        ha="center", va="top", color="black", fontsize=10, linespacing=1.45)

arrow((2.45, 6.6), (2.9, 6.6))
arrow((4.95, 6.6), (5.45, 6.6))
arrow((8.5, 7.0), (9.0, 7.0), "append")
arrow((8.5, 5.6), (9.0, 5.1), "upsert", ly=0.2)
arrow((2.45, 3.2), (2.9, 3.2))
arrow((4.95, 3.55), (5.45, 4.05), "marker", ly=0.14)
arrow((6.95, 3.55), (6.95, 3.3))
arrow((4.95, 2.8), (5.45, 2.6), "file", ly=-0.3)
arrow((9.0, 6.2), (8.5, 3.2), "re-read one day", rad=0.35, lx=-0.45, ly=0.0)
arrow((8.5, 2.95), (9.0, 3.45), "write", ly=0.05, lx=-0.15)
arrow((8.5, 2.3), (9.0, 2.4), "files", ly=-0.3)
arrow((11.55, 4.6), (12.05, 5.7), "query", lx=-0.15)
arrow((13.35, 5.0), (13.35, 4.65))

plt.savefig("report/architecture_diagram.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved report/architecture_diagram.png")
