import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(11, 8.3))
ax.set_xlim(0, 11)
ax.set_ylim(0, 8.3)
ax.axis("off")

COLORS = {
    "source": "#2f6fed",
    "kafka": "#111827",
    "speed": "#e0912a",
    "batch": "#7c3aed",
    "storage": "#0f9d58",
    "serving": "#d33b3b",
    "text_light": "white",
}


def box(x, y, w, h, text, color, fontsize=9.5, textcolor="white"):
    b = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.06,rounding_size=0.08",
        linewidth=1.2, edgecolor="black", facecolor=color, zorder=2,
    )
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize, color=textcolor, weight="bold", zorder=3, wrap=True)


def arrow(x1, y1, x2, y2, text=None, style="-|>", color="#333333", curve=0.0):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14,
                         linewidth=1.4, color=color, zorder=1,
                         connectionstyle=f"arc3,rad={curve}")
    ax.add_patch(a)
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, fontsize=8, ha="center", color="#222")


# Sources
box(0.3, 6.6, 2.4, 0.9, "smart_meter_producer.py\n(streaming source)\nevery 2s / household", COLORS["source"])
box(0.3, 5.1, 2.4, 0.9, "tariff_batch_source.py\n(daily-batch source)\nCSV drop / sim-day", COLORS["source"])

# Kafka
box(3.2, 6.6, 2.0, 0.9, "Kafka\ntopic: smart-meter-readings\n(3 partitions)", COLORS["kafka"])

# Batch drop
box(3.2, 5.1, 2.0, 0.9, "Batch drop dir\ntariff_*.csv +\n_SUCCESS marker", COLORS["kafka"])

# Speed layer
box(5.8, 6.6, 2.4, 1.1, "SPEED LAYER\nSpark Structured Streaming\nwindowed agg by grid_zone\n(~10s micro-batches)", COLORS["speed"])

# Raw lake
box(5.8, 5.1, 2.4, 0.9, "Raw event archive\nParquet data lake\npartitioned by sim_day", COLORS["speed"], fontsize=9)

# Airflow + batch layer
box(3.2, 3.6, 2.0, 0.9, "Airflow DAG\ndaily_batch_pipeline\n(sensor -> spark-submit)", COLORS["batch"], fontsize=9)
box(5.8, 3.6, 2.4, 1.0, "BATCH LAYER\nSpark batch job\nrecompute totals + join\ntariff -> bill", COLORS["batch"])

# Postgres
box(2.7, 2.0, 5.6, 1.0,
    "PostgreSQL (serving store)\nlive_zone_metrics . alerts . pipeline_health\nhousehold_daily_consumption . tariff_reference . daily_billing_report",
    COLORS["storage"], fontsize=8.3)

# Serving
box(0.3, 0.3, 3.0, 0.9, "Observability\nJSON logs . alerts.py\n/metrics (Prometheus)", COLORS["serving"], fontsize=8.8)
box(3.6, 0.3, 2.6, 0.9, "FastAPI serving layer\n/api/grid/live\n/api/alerts\n/api/billing/*", COLORS["serving"], fontsize=8.5)
box(6.5, 0.3, 2.6, 0.9, "Dashboard\n(static HTML/JS,\nauto-refresh 5s)", COLORS["serving"], fontsize=9)

# Arrows
arrow(2.7, 7.05, 3.2, 7.05)
arrow(2.7, 5.55, 3.2, 5.55)
arrow(5.2, 7.05, 5.8, 7.05)
arrow(6.9, 6.6, 6.9, 6.0)
arrow(6.9, 5.1, 6.9, 4.6)
arrow(5.2, 5.55, 4.2, 4.5, curve=-0.2)
arrow(5.2, 4.05, 5.8, 4.05)
arrow(6.9, 5.1, 7.4, 4.6, curve=-0.2, color="#888")
arrow(5.8, 3.95, 4.2, 3.0, curve=0.2)
arrow(6.9, 3.6, 6.0, 3.0, curve=-0.15)
arrow(3.0, 2.5, 4.8, 1.2, curve=0.15)
arrow(6.5, 2.0, 4.9, 1.2, curve=-0.15)
arrow(4.9, 0.75, 3.6, 0.75)
arrow(6.2, 0.75, 6.5, 0.75)

ax.text(5.5, 8.05, "Smart Grid Energy Monitoring & Billing -- Lambda Architecture", fontsize=14, weight="bold", ha="center")
ax.text(5.5, 7.75, "Speed layer (fast, approximate)  +  Batch layer (accurate, replayable)  =  merged at query time by the API", fontsize=9.5, ha="center", color="#444")

plt.tight_layout()
plt.savefig("report/architecture_diagram.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved report/architecture_diagram.png")
