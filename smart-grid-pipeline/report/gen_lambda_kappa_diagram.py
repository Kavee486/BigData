"""Renders the Lambda vs Kappa comparison figure (report/lambda_vs_kappa.png).
Run from the repo root: python report/gen_lambda_kappa_diagram.py"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.family"] = "Times New Roman"
fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))

# (fill, edge) per role, matching the architecture diagram's colours
KAFKA = ("#e5e7eb", "#374151")
SPEED = ("#fde8c8", "#c2410c")
BATCH = ("#e9d5ff", "#7e22ce")
SERVE = ("#bbf7d0", "#15803d")
REPLAY = ("#fee2e2", "#b91c1c")


def box(ax, x, y, w, h, text, colours):
    fill, edge = colours
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.07",
                                linewidth=1.5, edgecolor=edge, facecolor=fill, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10.5, color="black", zorder=3)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12,
                                 linewidth=1.2, color="black", zorder=1))


ax = axes[0]
ax.set_xlim(0, 6); ax.set_ylim(0, 6); ax.axis("off")
ax.set_title("(a) Lambda architecture (chosen)", fontsize=13, weight="bold")
box(ax, 0.2, 4.6, 2.4, 0.95, "Raw events\n(Kafka)", KAFKA)
box(ax, 3.3, 4.6, 2.5, 0.95, "Speed layer\nfast, approximate", SPEED)
box(ax, 0.2, 2.8, 2.5, 1.05, "Batch layer\nexact, re-runnable\n(from data lake)", BATCH)
box(ax, 1.3, 0.9, 3.4, 1.0, "Serving layer merges\nspeed and batch views", SERVE)
arrow(ax, 2.6, 5.07, 3.3, 5.07)
arrow(ax, 1.4, 4.6, 1.4, 3.85)
arrow(ax, 4.55, 4.6, 3.9, 1.9)
arrow(ax, 1.6, 2.8, 2.3, 1.9)
ax.text(3, 0.25, "Two processing paths; the daily result is\nalways recomputed from the stored raw data.",
        fontsize=10, ha="center", color="black")

ax = axes[1]
ax.set_xlim(0, 6); ax.set_ylim(0, 6); ax.axis("off")
ax.set_title("(b) Kappa architecture (rejected)", fontsize=13, weight="bold")
box(ax, 0.2, 4.6, 2.4, 0.95, "Raw events\n(Kafka, long retention)", KAFKA)
box(ax, 3.3, 4.6, 2.5, 0.95, "Single stream\nprocessor", SPEED)
box(ax, 1.3, 2.7, 3.4, 1.05, "Corrections by replaying\nthe whole log through\na new job version", REPLAY)
box(ax, 1.3, 0.9, 3.4, 1.0, "Serving layer", SERVE)
arrow(ax, 2.6, 5.07, 3.3, 5.07)
arrow(ax, 4.5, 4.6, 3.6, 3.75)
arrow(ax, 3.0, 2.7, 3.0, 1.9)
ax.text(3, 0.25, "One processing path, but the daily tariff file is\nnot a natural stream and replays are costly.",
        fontsize=10, ha="center", color="black")

plt.tight_layout()
plt.savefig("report/lambda_vs_kappa.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved report/lambda_vs_kappa.png")
