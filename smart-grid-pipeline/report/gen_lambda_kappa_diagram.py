import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))

def box(ax, x, y, w, h, text, color, fontsize=8.6, textcolor="white"):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.07",
                        linewidth=1.1, edgecolor="black", facecolor=color, zorder=2)
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            color=textcolor, weight="bold", zorder=3)

def arrow(ax, x1, y1, x2, y2, color="#333"):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12,
                         linewidth=1.3, color=color, zorder=1)
    ax.add_patch(a)

# ---- Lambda (chosen) ----
ax = axes[0]
ax.set_xlim(0, 6); ax.set_ylim(0, 6); ax.axis("off")
ax.set_title("Lambda (chosen)", fontsize=12, weight="bold")
box(ax, 0.3, 4.6, 2.4, 0.9, "Raw events\n(Kafka)", "#111827")
box(ax, 3.3, 4.6, 2.4, 0.9, "Speed layer\n(Spark Streaming)\napprox., low-latency", "#e0912a")
box(ax, 3.3, 2.9, 2.4, 0.9, "Batch layer\n(Spark batch,\nParquet lake)\naccurate, replayable", "#7c3aed")
box(ax, 1.5, 1.0, 3.3, 1.0, "Serving layer merges\nspeed view + batch view\n(Postgres + FastAPI)", "#0f9d58")
arrow(ax, 2.7, 5.05, 3.3, 5.05)
arrow(ax, 1.5, 4.6, 1.5, 3.6)
arrow(ax, 1.5, 3.6, 3.3, 3.35)
arrow(ax, 4.5, 4.6, 4.5, 3.8)
arrow(ax, 4.0, 4.6, 3.2, 2.0)
arrow(ax, 4.5, 2.9, 3.2, 2.0)
ax.text(3, 0.3, "Two code paths, but a correct,\nreplayable batch view every day.", fontsize=8, ha="center", color="#333")

# ---- Kappa (rejected) ----
ax = axes[1]
ax.set_xlim(0, 6); ax.set_ylim(0, 6); ax.axis("off")
ax.set_title("Kappa (rejected for this use case)", fontsize=12, weight="bold")
box(ax, 0.3, 4.6, 2.4, 0.9, "Raw events\n(Kafka, long retention)", "#111827")
box(ax, 3.3, 4.6, 2.4, 0.9, "Single stream processor\n(Spark Streaming)\none code path", "#e0912a")
box(ax, 1.5, 2.6, 3.3, 1.0, "Reprocess by REPLAYING\nthe whole log through the\nsame job when tariff\nsemantics change", "#b23b3b")
box(ax, 1.5, 1.0, 3.3, 1.0, "Serving layer\n(Postgres + FastAPI)", "#0f9d58")
arrow(ax, 2.7, 5.05, 3.3, 5.05)
arrow(ax, 4.5, 4.6, 3.2, 3.6)
arrow(ax, 3.2, 2.6, 3.2, 2.0)
ax.text(3, 0.3, "Elegant, but the daily tariff file\nisn't naturally a stream, and full replay\nfor one late file is costly overkill here.", fontsize=8, ha="center", color="#333")

plt.tight_layout()
plt.savefig("report/lambda_vs_kappa.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved")
