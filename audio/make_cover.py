#!/usr/bin/env python3
"""Generate square audiobook cover art for the manuscript and its SI.

Outputs cover_main.png and cover_si.png at 1600x1600, using the wordmark,
subtitle, authors, institution, and palette from config.py / config.typ.

The motif is a deliberately generic abstract one: faint scattered points with
brighter vertical strokes over them. It is the one part of this scaffold you
should feel free to throw away and replace with something that means something
for your own paper.
"""
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import config  # noqa: E402

HERE = Path(__file__).resolve().parent


def cover(out, badge, subtitle):
    random.seed(7)  # fixed, so regenerating does not churn the file bytes
    fig = plt.figure(figsize=(8, 8), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=config.COVER_BG, zorder=0))

    # --- motif: scattered points + brighter vertical strokes -----------------
    for _ in range(500):
        ax.plot(random.uniform(0, 1), random.uniform(0, 1), ".",
                color=config.COVER_MUTED, alpha=random.uniform(0.05, 0.18),
                ms=random.uniform(1, 3), zorder=1)
    for _ in range(34):
        x = random.uniform(0.04, 0.96)
        y0 = random.uniform(0.30, 0.62)
        h = random.uniform(0.12, 0.40)
        c = random.choice([config.COVER_ACCENT, config.COVER_ACCENT2])
        ax.plot([x, x], [y0, y0 + h], color=c,
                alpha=random.uniform(0.20, 0.85),
                lw=random.uniform(1.2, 3.2), solid_capstyle="round", zorder=2)

    # --- wordmark + subtitle -------------------------------------------------
    # Shrink the wordmark for long names so it stays inside the canvas.
    size = 104 if len(config.WORDMARK) <= 8 else max(48, int(830 / len(config.WORDMARK)))
    ax.text(0.5, 0.60, config.WORDMARK, ha="center", va="center",
            fontsize=size, fontweight="bold", color=config.COVER_FG, zorder=5)
    ax.text(0.5, 0.485, subtitle, ha="center", va="center",
            fontsize=18.5, color="#cbd5e1", zorder=5, wrap=True,
            fontstyle="italic")

    # --- badge pill ----------------------------------------------------------
    ax.add_patch(FancyBboxPatch((0.355, 0.30), 0.29, 0.062,
                 boxstyle="round,pad=0.008,rounding_size=0.03",
                 fc="none", ec=config.COVER_ACCENT, lw=2.2, zorder=5,
                 transform=ax.transAxes))
    ax.text(0.5, 0.331, badge, ha="center", va="center",
            fontsize=15, color=config.COVER_ACCENT, fontweight="bold", zorder=6)

    # --- authors + affiliation -----------------------------------------------
    ax.text(0.5, 0.15, config.COVER_AUTHORS, ha="center",
            va="center", fontsize=17, color=config.COVER_FG, zorder=5)
    ax.text(0.5, 0.105, config.INSTITUTION, ha="center",
            va="center", fontsize=13, color=config.COVER_MUTED, zorder=5)

    fig.savefig(out, facecolor=config.COVER_BG, metadata={"Software": None})
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    cover(HERE / "cover_main.png", "AUDIOBOOK", config.COVER_SUBTITLE)
    cover(HERE / "cover_si.png", "SUPPORTING INFORMATION", config.COVER_SUBTITLE)
