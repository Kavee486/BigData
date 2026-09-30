"""Renders the report's architecture figure (report/architecture_diagram.png).
Run from the repo root: python report/gen_diagram.py

Layered view: sources -> ingestion -> processing (speed + batch) -> storage ->
serving, with observability as a cross-cutting band. Arrows are coloured by
path (speed, batch, serving) and the processing/storage gap is wide enough
for every arrow to run straight and carry a readable label."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Times New Roman"

fig, ax = plt.subplots(figsize=(16.5, 9.4))
ax.set_xlim(0, 16.5)
ax.set_ylim(0, 9.4)
ax.axis("off")

FILL = {"plain": "white", "source": "#dbeafe", "ingest": "#e5e7eb", "speed": "#fde8c8", "batch": "#e9d5ff",
        "lake": "#d1fae5", "db": "#bbf7d0", "files": "#ecfccb", "serve": "#fee2e2", "obs": "#e0f2fe"}
EDGE = {"source": "#1d4ed8", "ingest": "#374151", "speed": "#c2410c", "batch": "#7e22ce", "lake": "#047857",
        "db": "#15803d", "files": "#4d7c0f", "serve": "#b91c1c", "obs": "#0369a1", "plain": "black"}
# Arrow colours by path
C_IN, C_SPEED, C_BATCH, C_READ, C_SERVE = "#111827", "#c2410c", "#7e22ce", "#047857", "#b91c1c"
C_CTRL = "#6b7280"  # orchestration control: checks/reads only, no data produced


def box(x, y, w, h, title, body, fill="plain", fs=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
                                linewidth=1.6, edgecolor=EDGE[fill], facecolor=FILL[fill], zorder=2))
    ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="top", fontsize=fs + 1.5, color="black",
            weight="bold", zorder=3)
    ax.text(x + w / 2, y + h - 0.58, body, ha="center", va="top", fontsize=fs, color="black", zorder=3,
            linespacing=1.3)


def label(x, y, text, color):
    ax.text(x, y, text, fontsize=10, ha="center", va="center", color=color, style="italic", weight="bold",
            zorder=6, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))


def arrow(p1, p2, color=C_IN, text=None, lx=0.0, ly=0.2, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=20, linewidth=2.0, color=color,
                                 zorder=5, linestyle=ls, shrinkA=0, shrinkB=0))
    if text:
        label((p1[0] + p2[0]) / 2 + lx, (p1[1] + p2[1]) / 2 + ly, text, color)


def route(points, color, text=None, at=None, ls="-"):
    """Orthogonal arrow through the given points; arrowhead on the last segment."""
    xs, ys = zip(*points[:-1])
    ax.plot(xs, ys, color=color, linewidth=2.0, linestyle=ls, zorder=5, solid_capstyle="butt")
    arrow(points[-2], points[-1], color, ls=ls)
    if text:
        label(at[0], at[1], text, color)


# ---- layer frames -----------------------------------------------------------
layers = [(0.15, 2.45, "Sources"), (2.75, 2.35, "Ingestion"), (5.3, 3.35, "Processing"),
          (10.25, 2.85, "Storage"), (13.3, 3.05, "Serving")]
for x, w, name in layers:
    ax.add_patch(Rectangle((x, 1.75), w, 6.55, facecolor="white", edgecolor="black", linestyle=(0, (4, 3)),
                           linewidth=0.8, zorder=0))
    ax.text(x + w / 2, 8.1, name, ha="center", fontsize=13, weight="bold", color="black")

# ---- components ---------------------------------------------------------------
box(0.3, 5.75, 2.15, 1.75, "Smart meters", "24 households, 4 zones\none reading every 2 s\n~1% faulty readings", "source")
box(0.3, 2.35, 2.15, 1.75, "Tariff extract", "one CSV file per\nsimulated day,\npublished after the\nday ends", "source")

box(2.9, 5.75, 2.05, 1.75, "Apache Kafka", "meter readings topic\n3 partitions\nkeyed by household", "ingest")
box(2.9, 2.35, 2.05, 2.3, "Landing area", "daily tariff file\n+ completion marker", "ingest")

box(5.45, 5.35, 3.05, 2.5, "Speed layer",
    "Spark Structured Streaming\nvalidate and clean readings\n30 s windows per zone\n(load, solar, renewable %)\narchive clean readings\nrunning household totals", "speed")
box(5.45, 4.05, 3.05, 1.0, "Apache Airflow", "schedules the daily job: wait for file,\nrun Spark, publish report, check alerts", "batch", fs=10)
box(5.45, 1.95, 3.05, 1.75, "Batch layer", "Spark batch job per day\nexact totals, tariff join,\nbills, reconciliation", "batch")

box(10.4, 6.0, 2.55, 1.85, "Parquet data lake", "raw readings\norganised by day\n(never changed)\nrejected readings", "lake")
box(10.4, 3.6, 2.55, 2.15, "PostgreSQL", "live zone figures\nlive household totals\ndaily bills\nreconciliation results\nalerts and health", "db")
box(10.4, 1.95, 2.55, 1.05, "Report files", "daily CSV and\nHTML report", "files")

box(13.45, 5.0, 2.75, 2.85, "REST API", "live grid view\ndaily billing report\nprovisional bills\n(speed + batch merge)\nalerts, health,\nmetrics", "serve")
box(13.45, 1.95, 2.75, 2.7, "Dashboard", "live zone view\nalerts and health\nprovisional and\nfinal bills", "serve")

ax.add_patch(FancyBboxPatch((0.3, 0.1), 15.9, 1.45, boxstyle="round,pad=0.04,rounding_size=0.08",
                            facecolor=FILL["obs"], edgecolor=EDGE["obs"], linewidth=1.6, zorder=2))
ax.text(8.25, 1.45, "Observability (all layers)", ha="center", va="top", color="black", weight="bold", fontsize=12)
ax.text(8.25, 1.08, "structured JSON logs from every component   |   component heartbeats and health check\n"
        "alert rules: low renewable share, missing data, failed component, invalid data rate, processing lag, speed/batch drift, failed Airflow task\n"
        "Prometheus metrics and alert rules   |   Spark and Airflow monitoring interfaces",
        ha="center", va="top", color="black", fontsize=10, linespacing=1.45)

# ---- arrows ---------------------------------------------------------------------
# sources -> ingestion -> processing
arrow((2.45, 6.6), (2.9, 6.6))
arrow((4.95, 6.6), (5.45, 6.6))
arrow((2.45, 3.2), (2.9, 3.2))
arrow((4.95, 4.45), (5.45, 4.45), C_BATCH, "marker", ly=0.22)
arrow((4.95, 2.8), (5.45, 2.8), C_BATCH, "file", ly=0.22)
arrow((6.97, 4.05), (6.97, 3.7), C_BATCH)

# processing -> storage (wide gap between x = 8.5 and 10.4)
GX = 9.3  # label column in the gap
arrow((8.5, 7.3), (10.4, 7.3), C_SPEED, "store clean\nreadings", lx=-0.15, ly=0.33)
arrow((8.5, 5.55), (10.4, 5.55), C_SPEED, "update live\nfigures", lx=-0.15, ly=0.33)
arrow((8.5, 3.65), (10.4, 3.65), C_BATCH, "write bills\n(one transaction)", lx=-0.15, ly=0.35)
# Airflow's own steps only check/read PostgreSQL: which days are billed, and the bills for the report
arrow((8.5, 4.55), (10.4, 4.55), C_CTRL, "check billed days,\nread bills for report", lx=-0.28, ly=0.33, ls=":")
# batch layer re-reads one day of raw readings from the lake (dashed, routed along the storage edge)
route([(10.4, 6.35), (10.05, 6.35), (10.05, 2.95), (8.5, 2.95)], C_READ, ls=(0, (5, 3)),
      text="read one day\nfrom the lake", at=(GX - 0.15, 2.55))
# Airflow's publish-report step turns that day's bills into the CSV + HTML report files
arrow((11.675, 3.6), (11.675, 3.0), C_BATCH)
label(12.35, 3.3, "report step\n(Airflow)", C_BATCH)

# storage -> serving
arrow((12.95, 5.4), (13.45, 5.4), C_SERVE, "query", ly=0.22)
arrow((14.82, 5.0), (14.82, 4.65), C_SERVE)

# ---- legend -----------------------------------------------------------------------
handles = [Line2D([], [], color=C_IN, lw=2, label="ingestion"),
           Line2D([], [], color=C_SPEED, lw=2, label="speed layer (live, every 10 s)"),
           Line2D([], [], color=C_BATCH, lw=2, label="batch layer (once per simulated day)"),
           Line2D([], [], color=C_READ, lw=2, ls=(0, (5, 3)), label="batch layer reads stored readings"),
           Line2D([], [], color=C_CTRL, lw=2, ls=":", label="Airflow control (checks and reads)"),
           Line2D([], [], color=C_SERVE, lw=2, label="serving")]
ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, fontsize=10.5,
          handlelength=2.6)

plt.savefig("report/architecture_diagram.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved report/architecture_diagram.png")
