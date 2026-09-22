#!/usr/bin/env python3
"""Write ../../figures/toc_graphic.png -- the graphical abstract (TOC graphic).

A placeholder, like the prose: replace the drawing, keep the contract. The
journal wants this graphic on its own terms, which are not a plot's: it must
fit a fixed box (ACS: 3.25 x 1.75 in at 300 dpi), say what the paper is about
without stating a result, and not repeat a figure from the text. So this is a
schematic, not data, and it is sized to the box exactly -- 975 x 525 px --
which is what `just check-journal` measures it against.

A graphical abstract is often drawn by hand rather than generated. That is
fine: put the file under figures/, run `just adopt note="drawn in ..."`, and
reference it as fig("fig.toc") all the same. Delete this script when you do,
or the next `just assets` writes the placeholder back.

Picked up by `just assets` on the filename pattern gen_*_figure.py.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

from _assets import record

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent          # analysis/scripts/ -> analysis/ -> paper/
OUT = PAPER / "figures" / "toc_graphic.png"

WIDTH_IN, HEIGHT_IN, DPI = 3.25, 1.75, 300


def main() -> int:
    fig = plt.figure(figsize=(WIDTH_IN, HEIGHT_IN), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH_IN)
    ax.set_ylim(0, HEIGHT_IN)
    ax.axis("off")

    # Three stages of the pipeline the scaffold encodes, as boxes and arrows.
    # Sans-serif at 8 pt, the size the ACS guideline asks for.
    stages = [("Analysis", "#dbeafe"), ("Declarations", "#bfdbfe"), ("Manuscript", "#93c5fd")]
    box_w, box_h, gap = 0.85, 0.55, 0.30
    x0 = (WIDTH_IN - (3 * box_w + 2 * gap)) / 2
    y0 = 0.72
    for i, (label, color) in enumerate(stages):
        x = x0 + i * (box_w + gap)
        ax.add_patch(FancyBboxPatch((x, y0), box_w, box_h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    linewidth=0.8, edgecolor="#1e3a8a", facecolor=color))
        ax.text(x + box_w / 2, y0 + box_h / 2, label, ha="center", va="center",
                fontsize=8, family="sans-serif", color="#1e3a8a")
        if i < 2:
            ax.add_patch(FancyArrowPatch((x + box_w + 0.03, y0 + box_h / 2),
                                         (x + box_w + gap - 0.03, y0 + box_h / 2),
                                         arrowstyle="-|>", mutation_scale=10,
                                         linewidth=0.8, color="#1e3a8a"))
    ax.text(WIDTH_IN / 2, 0.38, "numbers, figures and tables by id",
            ha="center", va="center", fontsize=8, family="sans-serif", color="#334155")
    ax.text(WIDTH_IN / 2, 1.50, "one source, every output",
            ha="center", va="center", fontsize=8, family="sans-serif",
            color="#0f172a", weight="bold")

    OUT.parent.mkdir(exist_ok=True)
    # Deterministic bytes, as every generator here: no creation date in the PNG.
    fig.savefig(OUT, dpi=DPI, metadata={"Software": None})
    plt.close(fig)
    record("fig.toc", str(OUT.relative_to(PAPER)), kind="figure",
           desc="Graphical abstract (TOC graphic), sized to the journal's box")
    print(f"wrote {OUT.relative_to(PAPER)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
