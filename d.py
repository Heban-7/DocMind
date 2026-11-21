#!/opt/jupyterhub/bin/python
"""Fruh — model performance across the training iterations (German labels).

Two panels, in the style of mpm-service/model_progress_graph.py:

  * Image-level performance (Accuracy / F1) per model iteration.
  * Defect-level accuracy and F1 for the only two relevant classes — separately
    and combined in one panel (accuracy solid, F1 dashed),
    ``Inclusions`` and ``Scratches``. All other classes present in some
    model outputs (``Edge Case``, ``Inclusions2``, ``Inclusions_Brenner``)
    are single-occurrence artefacts and are deliberately excluded.

Image-level numbers and the per-class F1 values are taken from
``fruh/presentation.html`` (slides "Accuracy, Recall and F1 in direct
comparison" and "Class accuracy across all models").

Per-class accuracy is not contained in the presentation, so it was recomputed
from the database with the ``utils/eval.py`` API: for each class, an image
counts as positive if it carries that class, and the accuracy is
``(TP + TN) / images`` at the confidence threshold that reproduces the
presentation F1 of the same model (M0 0.15, M1 0.25, M2 0.45, M4 0.20,
M5 0.50). Model / test-set / epoch used:
  M0 v1.0_DETR_Model set 101 ep 1, M1 v2.0_DETR_Model set 212 ep 1,
  M2 v2.1_DETR _Model set 212 ep 3, M4 v3.1_DETR_Model set 214 ep 80,
  M5 v3.4_DETR _Tile_Model set 214 ep 43.

Model 3 (v3.0, epoch 3) is an under-trained checkpoint of the same dataset as
Model 4 and is excluded from the charts on request; five iterations are shown
and the original model numbers (0, 1, 2, 4, 5) are kept for traceability.

Usage:
    /opt/jupyterhub/bin/python model_progress_graph.py
    /opt/jupyterhub/bin/python model_progress_graph.py --outdir ./reports --dpi 200
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt

# --- Data: performance across model iterations -----------------------------
# Source: fruh/presentation.html
TRAINING_PROGRESS = [
    {
        "name": "0",
        "image_level": {"accuracy": 0.714,  "f1_score": 0.80},
        "defect_level": {
            "Scratch": {"accuracy": 0.714,  "f1_score": 0.80}
        },
    },
    {
        "name": "1",
        "image_level": {"accuracy": 0.875, "f1_score": 0.8571},
        "defect_level": {
            "Scratch": {"accuracy": 0.875, "f1_score": 0.8571},
        },
    },
    {
        "name": "2",
        "image_level": {"accuracy": 1.00, "f1_score": 1.00},
        "defect_level": {
            "Scratch": {"accuracy": 1.00, "f1_score": 1.00},
        },
    }
]

# Colors
IMG_COLORS = {"accuracy": "#3b82f6", "f1_score": "#8b5cf6"}
IMG_MARKERS = {"accuracy": "o", "f1_score": "d"}
IMG_LABELS = {"accuracy": "Accuracy", "f1_score": "F1-Score"}

DEFECT_COLORS = {"Scratch": "#f59e0b"}
DEFECT_LABELS = {"Scratch": "Kratzer"}

# Light theme (white page, for print/slides)
BG_FIG = "#ffffff"   # figure / page background
BG_AX = "#ffffff"    # plot background
FG = "#1f2937"       # dark text / ticks
GRID = "#94a3b8"     # grid lines
SEP = "#64748b"      # image-set separator lines
BAND = "#f1f5f9"     # alternating image-set band

# Which training image set each model iteration was trained on.
# Modell 0 -> set 1, Modell 1+2 -> set 2, Modell 3+4 -> set 3.
IMAGE_SET_OF_MODEL = {"0": 1, "1": 2, "2": 2}
SET_LABELS = {1: "Manuelle Annotation", 2: "Kunden-Annotation"}


def _style_axes(ax) -> None:
    """Apply the dark-blue theme and remove the bounding box (spines)."""
    ax.set_facecolor(BG_AX)
    for name, spine in ax.spines.items():
        spine.set_visible(name in ("left", "bottom"))
        spine.set_color("#cbd5e1")
    ax.tick_params(colors=FG)
    ax.xaxis.label.set_color(FG)
    ax.yaxis.label.set_color(FG)
    ax.title.set_color(FG)


def _mark_image_sets(ax) -> None:
    """Shade and label the training-image-set groups along the x axis."""
    sets = [IMAGE_SET_OF_MODEL[m["name"]] for m in TRAINING_PROGRESS]
    groups, start = [], 0
    for i in range(1, len(sets) + 1):
        if i == len(sets) or sets[i] != sets[start]:
            groups.append((sets[start], start, i - 1))
            start = i

    for k, (set_no, lo, hi) in enumerate(groups):
        if k % 2 == 1:
            ax.axvspan(lo - 0.5, hi + 0.5, color=BAND, zorder=0)
        if lo > 0:
            ax.axvline(lo - 0.5, color=SEP, linewidth=1.2, linestyle=":",
                       alpha=0.8, zorder=1)
        label = SET_LABELS.get(set_no, f"Satz {set_no}")
        ax.annotate(label, xy=((lo + hi) / 2, 1.0),
                    xycoords=("data", "axes fraction"), xytext=(0, -14),
                    textcoords="offset points", ha="center", va="top",
                    fontsize=10, fontweight="bold", color=SEP, zorder=4)
    ax.set_xlim(-0.5, len(sets) - 0.5)


def _annotate(ax, xs, ys, color, dy: int = 9) -> None:
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points",
                    xytext=(0, dy), ha="center", fontsize=9, color=color)


def plot_image_level(ax) -> None:
    labels = [f"Modell {m['name']}" for m in TRAINING_PROGRESS]
    xs = list(range(len(labels)))

    for key in ("accuracy", "f1_score"):
        ys = [m["image_level"][key] * 100 for m in TRAINING_PROGRESS]
        ax.plot(xs, ys, color=IMG_COLORS[key], marker=IMG_MARKERS[key],
                markersize=7, linewidth=2.5, label=IMG_LABELS[key], zorder=3)
        ax.fill_between(xs, ys, color=IMG_COLORS[key], alpha=0.07, zorder=2)
        # accuracy annotated below the marker so it cannot collide with F1
        _annotate(ax, xs, ys, IMG_COLORS[key], dy=9 if key == "f1_score" else -16)

    ax.set_title("Performance auf Bildebene", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Punktzahl (%)")
    ax.set_xlabel("Modelliteration")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(80, 100)
    ax.grid(axis="y", color=GRID, alpha=0.25)
    _style_axes(ax)
    _mark_image_sets(ax)
    ax.legend(loc="lower right", frameon=True, facecolor=BG_AX,
              edgecolor="none", labelcolor=FG)


def _plot_defect(ax, metric: str, title: str, ylabel: str, ylim, legend_loc) -> None:
    labels = [f"Modell {m['name']}" for m in TRAINING_PROGRESS]
    xs = list(range(len(labels)))

    for cls, color in DEFECT_COLORS.items():
        ys = [m["defect_level"][cls][metric] * 100 for m in TRAINING_PROGRESS]
        ax.plot(xs, ys, color=color, marker="o", markersize=7, linewidth=2.5,
                label=DEFECT_LABELS[cls], zorder=3)
        ax.fill_between(xs, ys, color=color, alpha=0.07, zorder=2)
        _annotate(ax, xs, ys, color)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Modelliteration")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(*ylim)
    ax.grid(axis="y", color=GRID, alpha=0.25)
    _style_axes(ax)
    _mark_image_sets(ax)
    ax.legend(loc=legend_loc, frameon=True, facecolor=BG_AX,
              edgecolor="none", labelcolor=FG)


def plot_defect_level(ax) -> None:
    _plot_defect(ax, "f1_score", "Performance je Fehlerklasse (F1)",
                 "F1-Score (%)", (60, 100), "lower right")


def plot_defect_accuracy(ax) -> None:
    _plot_defect(ax, "accuracy", "Performance je Fehlerklasse (Accuracy)",
                 "Accuracy (%)", (60, 100), "lower right")


def plot_defect_combined(ax) -> None:
    """Accuracy (solid) and F1 (dashed) per defect class in one panel."""
    labels = [f"Modell {m['name']}" for m in TRAINING_PROGRESS]
    xs = list(range(len(labels)))

    for cls, color in DEFECT_COLORS.items():
        acc = [m["defect_level"][cls]["accuracy"] * 100 for m in TRAINING_PROGRESS]
        f1 = [m["defect_level"][cls]["f1_score"] * 100 for m in TRAINING_PROGRESS]
        ax.plot(xs, acc, color=color, marker="o", markersize=7, linewidth=2.5,
                label=f"{DEFECT_LABELS[cls]} — Accuracy", zorder=3)
        ax.plot(xs, f1, color=color, marker="d", markersize=6, linewidth=2.2,
                linestyle="--", label=f"{DEFECT_LABELS[cls]} — F1", zorder=3)
        # keep the two class curves' value labels on opposite sides
        _annotate(ax, xs, acc, color, dy=10 if cls == "Scratch" else -17)
        _annotate(ax, xs, f1, color, dy=10 if cls == "Scratch" else -17)

    ax.set_title("Performance je Fehlerklasse (Accuracy & F1)",
                 fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Punktzahl (%)")
    ax.set_xlabel("Modelliteration")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(55, 102)
    ax.grid(axis="y", color=GRID, alpha=0.25)
    _style_axes(ax)
    _mark_image_sets(ax)
    ax.legend(loc="lower right", fontsize=9, ncol=2, frameon=True, facecolor=BG_AX,
              edgecolor="none", labelcolor=FG)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Cardiobridge model training progress graphs.")
    parser.add_argument("--outdir",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports"),
                        help="Directory to write PNG files (default: ./reports)")
    parser.add_argument("--dpi", type=int, default=180, help="Output DPI (default: 180)")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # Combined figure (both panels side by side)
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    fig.patch.set_facecolor(BG_FIG)
    fig.suptitle("Modellentwicklung — Leistung über 5 Iterationen (gruppiert nach Trainings-Bildsatz)",
                fontsize=16, fontweight="bold", color=FG)
    plot_image_level(axes[0][0])
    plot_defect_combined(axes[0][1])
    plot_defect_level(axes[1][0])
    plot_defect_accuracy(axes[1][1])
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    combined = os.path.join(args.outdir, "model_progress.png")
    fig.savefig(combined, dpi=args.dpi, bbox_inches="tight", facecolor=BG_FIG)
    plt.close(fig)

    # Individual panels
    f1, a1 = plt.subplots(figsize=(14, 7)); f1.patch.set_facecolor(BG_FIG); plot_image_level(a1)
    p_img = os.path.join(args.outdir, "model_progress_image_level.png")
    f1.tight_layout(); f1.savefig(p_img, dpi=args.dpi, bbox_inches="tight", facecolor=BG_FIG); plt.close(f1)

    f2, a2 = plt.subplots(figsize=(14, 7)); f2.patch.set_facecolor(BG_FIG); plot_defect_level(a2)
    p_def = os.path.join(args.outdir, "model_progress_defect_level.png")
    f2.tight_layout(); f2.savefig(p_def, dpi=args.dpi, bbox_inches="tight", facecolor=BG_FIG); plt.close(f2)

    f3, a3 = plt.subplots(figsize=(14, 7)); f3.patch.set_facecolor(BG_FIG); plot_defect_accuracy(a3)
    p_acc = os.path.join(args.outdir, "model_progress_defect_level_accuracy.png")
    f3.tight_layout(); f3.savefig(p_acc, dpi=args.dpi, bbox_inches="tight", facecolor=BG_FIG); plt.close(f3)

    f4, a4 = plt.subplots(figsize=(14, 7)); f4.patch.set_facecolor(BG_FIG); plot_defect_combined(a4)
    p_both = os.path.join(args.outdir, "model_progress_defect_level_accuracy_f1.png")
    f4.tight_layout(); f4.savefig(p_both, dpi=args.dpi, bbox_inches="tight", facecolor=BG_FIG); plt.close(f4)

    print("Saved:")
    for p in (combined, p_img, p_def, p_acc, p_both):
        print(f"  {p}")


if __name__ == "__main__":
    main()
